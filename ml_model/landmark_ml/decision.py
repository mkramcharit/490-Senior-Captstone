from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class RecognitionPolicy:
    minimum_similarity: float = .8
    minimum_support: int = 2
    minimum_margin: float = .03
    near_duplicate_similarity: float = .98
    near_duplicate_margin: float = .1

    def __post_init__(self):
        for value in (self.minimum_similarity, self.minimum_margin, self.near_duplicate_similarity, self.near_duplicate_margin):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Recognition thresholds must be finite and within [0, 1]')
        if type(self.minimum_support) is not int or self.minimum_support < 2:
            raise ValueError('Recognition consensus requires at least two references')

    def evaluate(self, result):
        winner = result['landmark_id']
        matches = result['top_matches']
        supporting = [row['score'] for row in matches if row['landmark_id'] == winner]
        competitors = [row['score'] for row in matches if row['landmark_id'] != winner]
        similarity = max(supporting)
        margin = similarity - max(competitors) if competitors else None
        consensus = (similarity >= self.minimum_similarity and len(supporting) >= self.minimum_support
                     and (margin is None or margin >= self.minimum_margin))
        near_duplicate = (similarity >= self.near_duplicate_similarity
                          and (margin is None or margin >= self.near_duplicate_margin))
        accepted = consensus or near_duplicate
        return {'accepted': accepted, 'reason': 'retrieval_evidence_passed' if accepted else 'insufficient_retrieval_evidence',
                'supporting_references': len(supporting), 'competing_landmark_margin': margin,
                'policy': asdict(self), 'policy_validation': 'heuristic_not_accuracy_validated'}
