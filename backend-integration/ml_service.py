# DINOv2 & FAISS RECOGNITION ADAPTER
# DINOv2 + FAISS recognition adapter for Trekmark's /api/predict endpoint.
#
# Loads local model and either an SQ8 index or flat IP index.
# Preprocessing, CLS embeddings and normalizations match team's workflow.
# Predictions use the closest image, so repeated lower-quality images will not
# vote against a very close match. Match confidence is not calibrated accuracy.

# IMPORTS
# hashlib is used to verify that model and index files match the expected signature.
# json is used to read reference and output formatting.
# os is used to load configuration.
#
# threading is used to coordinate loading and prediction.
# Pillow can read bytes using BytesIO.
# Path is used for resolving local assets.
# Heavy ML dependencies are loaded when a recognizer is created.
import hashlib
import json
import os
import threading
from io import BytesIO
from pathlib import Path

# MODULE ROOT AND SHARED RECOGNIZER
# ROOT is the location of this module.
# _pipeline is the LandmarkRecognizer used by this module.
# This value is not a team LandmarkPipeline, but rather the recognizer itself.
ROOT = Path(__file__).resolve().parent
_pipeline = None
# LOADING AND PREDICTION LOCKS
# _load_lock is used to prevent multiple recognizers from loading in parallel.
# _predict_lock is used to serialise calls to recognize_image()
# These locks are per Python process. Each server process will have its own
# locks and loaded assets.
_load_lock = threading.Lock()
_predict_lock = threading.Lock()


# CONFIGURATION ERROR
# MLConfigurationError is a subclass of RuntimeError. This is used to indicate
# missing or incompatible assets or errors in a recognizer configuration.
# These errors can be translated to unavailable by the API.
class MLConfigurationError(RuntimeError):
    pass


# RESOLVE ASSET PATHS
# asset_path() uses either the specified environment variable or the default.
# First resolves a user-home prefix if present and then resolves relative
# paths with respect to ROOT (the location of this module) rather than the
# current working directory. If the environment variable is an empty string,
# the default is not used.
def asset_path(variable, default):
    path = Path(os.getenv(variable, default)).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


# MODEL SIGNATURE
# model_signature() will check that config.json, preprocessor_config.json and
# model.safetensors exist in the model directory. These files are then read
# in order in chunks of up to 1 MiB and used to create
# a single SHA256 digest with a preprocessing signature prefix added to the result. This is
# used to verify that the model assets match the index metadata, but is not used
# to measure accuracy of recognition or to verify the source of the model files.
def model_signature(directory):
    digest = hashlib.sha256()
    for filename in ('config.json', 'preprocessor_config.json', 'model.safetensors'):
        path = directory / filename
        if not path.is_file():
            raise MLConfigurationError(f'Missing ML model file: {path}')
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    return 'dinov2-cls-rgb-exif-l2-v1:' + digest.hexdigest()


# AGGREGATE MATCHES RETURNED
# Use the match with the highest score as the result. Report agreement separately.
# Associate each FAISS score with the corresponding reference index position.
# Ignore negative index positions and non-finite scores.
# Map valid positions to integer landmark ID and clip scores to [-1,1].
# If no valid matches can be found, raise MLConfigurationError.
def aggregate_matches(scores, positions, landmark_ids):
    
    import numpy as np
    matches = []
    for score, position in zip(scores, positions):
        if int(position) < 0 or not np.isfinite(score):
            continue
        matches.append({'landmark_id': int(landmark_ids[int(position)]),
                        'score': float(np.clip(score, -1, 1))})
    if not matches:
        raise MLConfigurationError('The FAISS index returned no usable matches.')
    # SELECT CLOSEST REFERENCE
    # Sort matches by score in descending order and use the landmark ID of the first
    # match. Lower quality repeated references will not override the highest quality
    # reference. Returned nonnegative index positions will also be assumed to be
    # valid index positions.
    matches.sort(key=lambda match: match['score'], reverse=True)
    winner = matches[0]['landmark_id']
    # AGREEMENT AND SIMILARITY
    # similarity is the score of the returned reference with highest score.
    # agreement is the fraction of usable returned references that have the same landmark ID
    # as the highest score reference. Agreement is reported as additional information
    # and does not affect selection of the reference.
    # confidence is the similarity but with negative values replaced by zero.
    # confidence_calibrated is set to False and selection_method is set to
    # nearest_reference.
    # This confidence value is a similarity value and does not indicate a validated
    # probability of correct identification. There is no score threshold used to reject
    # predictions.
    similarity = matches[0]['score']
    agreement = sum(match['landmark_id'] == winner for match in matches) / len(matches)
    return {'landmark_id': winner, 'confidence': max(0.0, similarity),
            'similarity': similarity, 'agreement': agreement,
            'confidence_calibrated': False, 'selection_method': 'nearest_reference',
            'top_matches': matches}



# LOCATE ML ASSETS
# LandmarkRecognizer uses LANDMARK_MODEL_PATH and LANDMARK_INDEX_PATH when configured.
# Otherwise the default directories under ROOT are ml_assets/dinov2-small
# and ml_assets/faiss-index respectively. Configured paths can point elsewhere.
# The index will require both references.json and images.faiss before it is loaded.
# The model signature for the selected model will be computed.
class LandmarkRecognizer:
    def __init__(self):
        model_dir = asset_path('LANDMARK_MODEL_PATH', 'ml_assets/dinov2-small')
        index_dir = asset_path('LANDMARK_INDEX_PATH', 'ml_assets/faiss-index')
        for filename in ('images.faiss', 'references.json'):
            if not (index_dir / filename).is_file():
                raise MLConfigurationError(f'Missing ML index file: {index_dir / filename}')
        signature = model_signature(model_dir)
        try:
            # IMPORT ML DEPENDENCIES
            # FAISS, NumPy, PyTorch and the image model and image processor will be
            # imported.
            # A missing dependency will be turned into an MLConfigurationError with a
            # message about how to install the package. References to the modules will be
            # stored on the recognizer.
            import faiss
            import numpy as np
            import torch
            from transformers import AutoImageProcessor, AutoModel
        except ImportError as error:
            raise MLConfigurationError('ML dependencies are missing. Install the updated backend requirements.') from error
        self.faiss, self.np, self.torch = faiss, np, torch
        # READ REFERENCE DATA
        # references.json will be loaded as UTF-8 with optional byte order mark processing.
        # Version 1 of references is required and the reference data must match the computed
        # model signature. Mismatched reference data will not be combined with mismatched
        # models.
        with (index_dir / 'references.json').open(encoding='utf-8-sig') as stream:
            payload = json.load(stream)
        if payload.get('version') != 1 or payload.get('signature') != signature:
            raise MLConfigurationError('The model files do not match the index signature. Use the supplied DINOv2 folder unchanged.')
        # VERIFY INDEX
        # images.faiss will be loaded. The index must either be IndexScalarQuantizer or
        # IndexFlatIP with inner product distance. Other indices or distance types are not
        # allowed. Although the documentation describes SQ8, this only checks for the
        # scalar quantizer class and does not check the type of quantization for scalar
        # quantizer.
        self.index = faiss.read_index(str(index_dir / 'images.faiss'))
        if not isinstance(self.index, (faiss.IndexScalarQuantizer, faiss.IndexFlatIP)) or self.index.metric_type != faiss.METRIC_INNER_PRODUCT:
            raise MLConfigurationError('Expected a scalar-quantized or flat inner-product FAISS index.')
        # VERIFY REFERENCE MAPPINGS
        # There must be at least one reference and there must be one row of reference data
        # per indexed vector. The index must be trained and all of the rows must contain
        # an integer value for landmark_id. Boolean values are not valid integer values.
        # These are only checks on the structure of the reference mappings and do not
        # indicate that every landmark ID must exist in Neon. The database lookup will be
        # done at another stage.
        rows = payload.get('references')
        if not isinstance(rows, list) or len(rows) != self.index.ntotal or not rows or not self.index.is_trained:
            raise MLConfigurationError('The FAISS index and reference mapping counts do not match, or the index is empty/untrained.')
        if any(not isinstance(row, dict) or type(row.get('landmark_id')) is not int for row in rows):
            raise MLConfigurationError('Reference mappings must contain integer Neon landmark IDs.')
        # COMPACT ARRAY OF LANDMARK IDS
        # A compact array of landmark IDs will be created using the position of each vector
        # as an index. Once the array has been created, the reference data and metadata
        # can be released. The FAISS index and compact landmark ID array will be available
        # for predictions.
        self.landmark_ids = np.fromiter((row['landmark_id'] for row in rows), dtype=np.int64, count=len(rows))
        del rows, payload
        # SELECT INFERENCING DEVICE
        # LANDMARK_DEVICE will be read and whitespace stripped. If the requested device
        # is CUDA but CUDA is not available, a configuration error will be raised with a
        # request to use CPU. Other errors can occur during model loading.
        self.device = os.getenv('LANDMARK_DEVICE', 'cpu').strip()
        if self.device.startswith('cuda') and not torch.cuda.is_available():
            raise MLConfigurationError('CUDA was selected but is unavailable. Set LANDMARK_DEVICE=cpu.')
        # THREADING CONFIGURATION
        # The number of FAISS threads will be read with a default of four and constrained
        # to be between one and sixteen. This value will be used to set the number of
        # threads used in PyTorch on the CPU and later as the OpenMP number of threads
        # used by FAISS. If a non-integer value is used this will result in an
        # initialization
        # error and this will be caught by the shared loader when this value is accessed via
        # get_recognizer().
        self.threads = max(1, min(16, int(os.getenv('FAISS_THREADS', '4'))))
        torch.set_num_threads(self.threads)
        # LOAD LOCAL DINOv2
        # The model and preprocessing will be loaded from local files without attempts to
        # download any files missing from the requested model. The preprocessing will be
        # set to the value specified in the configuration and the weights must be
        # safetensors. The model will be moved to the requested device and set to evaluation
        # mode. The model type must be dinov2 and the hidden size must match the dimension
        # of the index. The dimension value will be obtained from the model files rather
        # than hardcoded in this module.
        self.processor = AutoImageProcessor.from_pretrained(str(model_dir), local_files_only=True, use_fast=False)
        self.model = AutoModel.from_pretrained(str(model_dir), local_files_only=True, use_safetensors=True).to(self.device).eval()
        if self.model.config.model_type != 'dinov2' or self.index.d != self.model.config.hidden_size:
            raise MLConfigurationError('The DINOv2 model dimensions do not match the FAISS index.')
        # SET NUMBER OF NEIGHBORS TO SEARCH
        # LANDMARK_TOP_K will be read with a default value of five and constrained to
        # between one and fifty. This determines the number of nearest references that will
        # be searched and returned. The reference with the highest score will be used as the
        # winner and not the majority vote of references.
        self.top_k = max(1, min(50, int(os.getenv('LANDMARK_TOP_K', '5'))))

    # PREDICTION THREADING
    # The API caller can run this function in a worker thread; recognize_image()
    # allows only one prediction at a time within this process.
    # The number of FAISS threads will also be set here which will also set the per thread
    # OpenMP number of threads. More accurately, this module provides no worker threading.
    # Instead, a worker thread would need to be provided by the API caller as needed.
    # If the instance's predict() function is called then the prediction lock will be
    # bypassed.
    def predict(self, content):
        from PIL import Image, ImageOps
        self.faiss.omp_set_num_threads(self.threads)
        # DECODE UPLOADED IMAGE
        # The image bytes will be decoded using Pillow via BytesIO.
        # If the image has more than 25000000 pixels then a ValueError will be raised.
        # EXIF image orientation will be applied. Image will be converted to RGB.
        # Apart from the pixel limit, this function does not impose an upload-byte
        # limit or an allowed-image-format filter. These checks could be
        # performed by the API caller.
        with Image.open(BytesIO(content)) as source:
            if source.width * source.height > 25000000:
                raise ValueError('Choose an image smaller than 25 megapixels.')
            image = ImageOps.exif_transpose(source).convert('RGB')
        try:
            # PREPROCESS AND EMBED
            # The image will be preprocessed by the model image processor to create a batch
            # of one image using PyTorch. The images will be moved to the requested device.
            # The model will be run without gradient computation. The CLS token from the
            # last
            # hidden state will be selected and then the embedding will be L2-normalized
            # along
            # the feature dimension. This uses pretrained weights and does not train the
            # model
            # during inference.
            inputs = self.processor(images=[image], return_tensors='pt').to(self.device)
            with self.torch.inference_mode():
                vector = self.model(**inputs).last_hidden_state[:, 0, :]
                vector = self.torch.nn.functional.normalize(vector, p=2, dim=1)
            # CREATE FAISS QUERY
            # The embedding will be moved to CPU and then to a contiguous float32 NumPy
            # array.
            # All values must be finite.
            # If a usable embedding was not created then a ValueError will be raised.
            # Inner products between normalized query and reference embeddings are
            # equivalent
            # to cosine similarity. Scalar quantization may result in approximation of
            # vectors
            # within the index.
            query = self.np.ascontiguousarray(vector.cpu().numpy(), dtype=self.np.float32)
            if not self.np.isfinite(query).all():
                raise ValueError('The image did not produce a usable embedding.')
            # SEARCH INDEX
            # The smaller of either top_k or the number of indexed vectors will be searched.
            # The scores and index positions for the first query will be passed to
            # aggregate_matches() The closest reference and additional match information
            # will
            # be returned. The converted image will be closed in the finally block
            # after either search or inference.
            scores, positions = self.index.search(query, min(self.top_k, self.index.ntotal))
            return aggregate_matches(scores[0], positions[0], self.landmark_ids)
        finally:
            image.close()


# LAZY RECOGNIZER LOADING
# get_recognizer() will return an existing recognizer if available. If not then
# the loading lock will be acquired and the recognizer will be checked again before
# initialization. _pipeline is only assigned after successful initialization so if
# initialization fails the recognizer can be attempted again on the next call.
def get_recognizer():
    global _pipeline
    if _pipeline is None:
        with _load_lock:
            if _pipeline is None:
                try:
                    _pipeline = LandmarkRecognizer()
                # HANDLE LOADING FAILURES
                # If an existing MLConfigurationError exists it will be preserved.
                # All other errors will be wrapped with a generic message about asset
                # loading and
                # the original exception will be used as the cause for backend diagnostic
                # purposes.
                # After successful loading the shared recognizer will be returned.
                except MLConfigurationError:
                    raise
                except Exception as error:
                    raise MLConfigurationError('The ML assets could not be loaded. Check paths, dependencies and the backend terminal.') from error
    return _pipeline


# BACKEND RECOGNITION FUNCTION ENTRY POINT
# recognize_image() will acquire the prediction lock, get the recognizer and then
# return the recognizer’s prediction dictionary. The prediction lock will also be
# held if the recognizer needs to be loaded on the first call. The caller is
# responsible for exception handling during prediction and the construction of the
# final response.
def recognize_image(content):
    with _predict_lock:
        return get_recognizer().predict(content)


# STATUS INFORMATION
# status() will return whether the recognizer is loaded and, if so, the dimension
# and number of vectors in the index. If no recognizer is loaded these values will be
# None. In either case confidence_calibrated is set to False.
# Calling status() does not load or run the model and does not perform validation
# of assets that have not yet been loaded.
def status():
    return {'loaded': _pipeline is not None,
            'vectors': int(_pipeline.index.ntotal) if _pipeline else None,
            'dimensions': int(_pipeline.index.d) if _pipeline else None,
            'confidence_calibrated': False}


# COMMAND LINE ENTRY POINT
# Run from backend-integration: python ml_service.py [optional-image-path]
# If run directly then .env.ml and .env will be loaded in order under ROOT.
# load_dotenv will use the default value override=False which means that values that
# were set prior to running load_dotenv or values that were already loaded via
# .env.ml will override values that were set via .env. This does not run when this
# module is imported by the API.
if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env.ml')
    load_dotenv(ROOT / '.env')
    # PRINT STATUS AND OPTIONAL PREDICTION
    # The recognizer will be loaded and a status in JSON format will be printed.
    # If an image path is passed then the image will be read as bytes, recognize_image()
    # will be called and the prediction dictionary will be printed in JSON format.
    # The image path passed from the command line is interpreted with respect to the
    # current working directory if it is not an absolute path. Errors are not caught
    # within this entry point.
    recognizer = get_recognizer()
    print(json.dumps(status(), indent=2))
    if len(sys.argv) > 1:
        print(json.dumps(recognize_image(Path(sys.argv[1]).read_bytes()), indent=2))
