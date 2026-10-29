/*
SHARED DESTINATION FORMAT
Image recognition and Neon featured destinations use a shared destination format.
Convert responses for Neon landmarks into a destination format usable by the
trip planning interface in the frontend.
*/

/*
SUPPORTED PRESET IDS
PRESET_IDS stores the eight known featured destination ids.
Use a Set to determine if a provided id is in this set of supported ids.
These are frontend defined preset ids, not numeric ids of Neon landmarks.
*/
const PRESET_IDS = new Set([
  'orlando',
  'tokyo',
  'paris',
  'amazon',
  'rio',
  'new-york',
  'great-wall',
  'amalfi',
]);

/*
RESOLVE A PRESET ID
If destination.presetId is supported, prefer it over destination.id.
If not, compare destination.id to the same list of supported ids.
Return null if neither matches one of the supported preset ids.
Optional chaining can be used when destination may be null or undefined
without errors during property access. Id comparison is case sensitive.
*/
export function presetIdFor(destination) {
  return PRESET_IDS.has(destination?.presetId)
    ? destination.presetId
    : PRESET_IDS.has(destination?.id)
      ? destination.id
      : null;
}

export function destinationFromResponse(data) {
  /*
  HANDLE UNKNOWN RECOGNITION
  Unknown is an expected outcome and is not a destination that can be
  used for trip planning. If the prediction_status is unknown return null
  immediately. The caller can display an unknown status instead of trying
  to access trip planning.
  */
  if (data?.prediction_status === 'unknown') return null;

  /*
  REQUIRE A LANDMARK RECORD
  destinationFromResponse() pulls the landmark from a response.
  Throw an error if landmark is not provided or if the landmark.id is null or undefined.
  The ID does not have to be a number and is not checked against a database.
  */
  const landmark = data?.landmark;
  if (!landmark || landmark.id === null || landmark.id === undefined) {
    throw new Error('The landmark service did not return a destination.');
  }

  /*
  VALIDATE A DESTINATION'S LOCATION
  Pull lat and long from the landmark in the response.
  Reject values that are empty strings, out of range, non-finite, or missing.
  Latitude must be between -90 and 90 and longitude must be between -180 and 180.
  Number() is used to check validity, so coercion to number is allowed instead of requiring
  a specific data type. Use Number() to convert valid lat and long values when creating a destination.
  */
  const lat = landmark.latitude, lng = landmark.longitude;
  if (
    lat === null || lat === undefined || lat === '' ||
    lng === null || lng === undefined || lng === '' ||
    !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng)) ||
    Math.abs(Number(lat)) > 90 || Math.abs(Number(lng)) > 180
  ) {
    throw new Error('This destination needs valid database coordinates before a trip can be planned.');
  }

  /*
  SELECT LANDMARK IMAGES
  Main images for landmarks come from the landmark in the response (from Neon).
  If landmark_photos is an array, merge landmark.image with landmark_photos.
  Filter out non-string values, blank strings and duplicates using a Set.
  Maintain original order to allow the main image to be the first selected.
  The returned array does not trim strings and this function does not validate images, hosts,
  or URL schemes. Hotel and restaurant images are not used as substitutes for landmark images.
  */
  const images = [...new Set(
    [landmark.image, ...(Array.isArray(data.landmark_photos) ? data.landmark_photos : [])]
      .filter(image => typeof image === 'string' && image.trim())
  )];

  /*
  IDENTIFY FEATURED RESPONSES
  Only responses where data.source is featured are considered to be featured responses.
  All other responses are considered recognition and are reflected in the returned object as such.
  Featured responses do not have recognition mode or confidence.
  */
  const featured = data.source === 'featured';

  /*
  VALIDATE SCORES
  validScore() will only accept numeric scores that are finite, between zero and one, inclusive.
  Negative numbers, numbers greater than one, NaN, and string representations of numbers are rejected.
  This check is for format and range of the score and does not represent any level of statistical validity.
  */
  const validScore = value =>
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1;

  /*
  SELECT A CALIBRATED PROBABILITY
  If confidence_probability is neither null nor undefined at the top level,
  prefer that over match_details.confidence_probability.
  Otherwise, look at match_details.confidence_probability.
  Only use this as a calibrated probability if the response is not a featured response
  and the top level confidence_calibrated is true and the probability passes validScore().
  A confidence_probability present only in the match_details object does not imply calibration.
  */
  const probability = data.confidence_probability ?? data.match_details?.confidence_probability;
  const calibrated = !featured && data.confidence_calibrated === true && validScore(probability);

  /*
  SELECT A RAW MATCH SCORE
  Prefer match_score, then match_details.match_score, then confidence.
  The nullish coalescing will preserve a valid zero value.
  Also preserve an invalid non-null value instead of falling back to a subsequent value.
  If calibration is accepted use the calibrated probability, otherwise use the raw score.
  Validate the selected score before displaying it.
  */
  const rawScore = data.match_score ?? data.match_details?.match_score ?? data.confidence;
  const score = calibrated ? probability : rawScore;

  /*
  FORMAT CATEGORY
  Convert category_name to text and strip one occurrence of Category: at the beginning
  (case-insensitively). Replace underscores with spaces.
  If the resulting string is empty set the value to Landmark.
  Whitespace trimming, duplicate-prefix removal, and database category formatting
  are not performed by this function.
  */
  const category = String(landmark.category_name || '')
    .replace(/^Category:/i, '')
    .replaceAll('_', ' ') || 'Landmark';

  /*
  RETURN THE SHARED DESTINATION
  Return a destination object for use by the React interface.
  This function maps values from a response, validates selected values, and formats displayed values.
  This function does not comprehensively validate destinations, store them,
  make network requests or interact with Neon.
  */
  return {
    /*
    FRONTEND AND DATABASE IDS
    Create a frontend id using the format: landmark-{landmark.id}
    Store landmarkId as the original database id.
    If the response is featured copy preset_id to presetId, otherwise null.
    This does not check the preset_id in the response against PRESET_IDS.
    */
    id: `landmark-${landmark.id}`,
    landmarkId: landmark.id,
    presetId: featured ? data.preset_id : null,
    source: featured ? 'featured' : 'recognition',

    /*
    NAME AND LOCATION FIELDS
    Pull in the city, state, country, and landmark name into the destination.
    countryName is simply the country from the response.
    country will combine truthy city, state, and country fields using commas as a separator.
    lat and lng are numeric values for latitude and longitude respectively.
    They match the format expected by the frontend.
    */
    name: landmark.name,
    city: landmark.city,
    state: landmark.state,
    countryName: landmark.country,
    country: [landmark.city, landmark.state, landmark.country].filter(Boolean).join(', '),
    lat: Number(lat),
    lng: Number(lng),

    /*
    DISPLAY CONFIDENCE
    If the response is not featured and a valid score is selected, multiply by 100 and round to an integer.
    Otherwise set confidence to null.
    Set confidenceCalibrated to the value of accepted calibration.
    A raw score does not represent the percentage of accuracy of a recognition.
    */
    confidence: !featured && validScore(score) ? Math.round(score * 100) : null,
    confidenceCalibrated: calibrated,

    /*
    CONFIDENCE LABEL AND DESCRIPTION
    If calibration is accepted use Estimated confidence. Otherwise use Match confidence.
    If calibration is accepted the description refers to estimated correctness probability
    for images that are similar to the images used in the calibration.
    If calibration is not accepted the description explains similarity to images and clarifies
    that this is not a verified probability of correctness.
    The labels and descriptions are defined here; score and calibration values come from the response.
    This function does not provide any calibration to a model or verify that all raw scores use the same calculation.
    */
    confidenceLabel: calibrated ? 'Estimated confidence' : 'Match confidence',
    confidenceDescription: calibrated
      ? 'Estimated correctness probability for photos comparable to the calibration set.'
      : 'Visual similarity to the closest reference image; not a verified probability of correctness.',

    /*
    INDEX INFORMATION
    If index_info is present in match_details and is truthy copy that value. Otherwise null.
    This function does not use index_info at the top level.
    */
    indexInfo: data.match_details?.index_info || null,

    /*
    MAIN IMAGE AND GALLERY
    Set hero and experienceImage to the first image that was retained. If no images are present set to an empty string.
    Set galleryImages to the array of all retained images.
    Set kicker and categoryName to the formatted category.
    */
    hero: images[0] || '',
    experienceImage: images[0] || '',
    categoryName: category,
    kicker: category,

    /*
    SUMMARY AND RECOGNITION MODE
    Create a short summary from the name of the landmark.
    If the response is a recognition response copy recognition_mode into recognitionMode.
    If it is a featured response set recognitionMode to null.
    This function does not perform any image recognition.
    */
    summary: `Explore ${landmark.name}, build your plan, and discover nearby places.`,
    recognitionMode: featured ? null : data.recognition_mode,
    galleryImages: images,

    /*
    NEARBY LANDMARKS
    If nearby_landmarks is present and truthy copy that value. Otherwise use an empty array.
    This function does not verify that nearby_landmarks is an array or its contents.
    */
    nearbyLandmarks: data.nearby_landmarks || [],

    /*
    TRIP SERVICE RESULTS
    If hotel_search is present and truthy copy that object from trip_suggestions. Otherwise null.
    If restaurant_search is present and truthy copy that object from trip_suggestions. Otherwise null.
    Use optional chaining to handle missing trip_suggestions.
    This function does not make or validate any of the search objects.
    */
    hotelSearch: data.trip_suggestions?.hotel_search || null,
    restaurantSearch: data.trip_suggestions?.restaurant_search || null,
  };
}