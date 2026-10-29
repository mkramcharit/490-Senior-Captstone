from collections import defaultdict
import numpy as np

from .calibration import metrics


def wilson_interval(correct, count):
    if count < 1 or not 0 <= correct <= count:
        raise ValueError('Use valid binomial counts')
    z = 1.96
    observed = correct / count
    center = (observed + z*z/(2*count)) / (1 + z*z/count)
    half = z * np.sqrt(observed*(1-observed)/count + z*z/(4*count*count)) / (1 + z*z/count)
    return [max(0., float(center-half)), min(1., float(center+half))]


def review_predictions(rows, protocol):
    if not rows:
        raise ValueError('Independent validation requires predictions')
    displayed = [row for row in rows if row['probability'] is not None]
    unsupported = [row for row in rows if not row['landmark_ids']]
    report = {'total_queries': len(rows), 'accepted_count': sum(row['accepted'] for row in rows),
              'displayed_probability_count': len(displayed), 'unsupported_queries': len(unsupported),
              'unsupported_false_acceptances': sum(row['accepted'] for row in unsupported),
              'eligible': False, 'failed_checks': []}
    if not displayed or not unsupported:
        report['failed_checks'].append('Insufficient accepted predictions or unsupported queries')
        return report
    probabilities = np.array([row['probability'] for row in displayed])
    correct = np.array([row['correct'] for row in displayed], dtype=float)
    raw = np.array([row['match_score'] for row in displayed])
    groups = defaultdict(list)
    for i, row in enumerate(displayed):
        groups[row['group_id']].append(i)
    clusters = list(groups.values())
    rng = np.random.default_rng(protocol['bootstrap_seed'])
    bias, brier = [], []
    for _ in range(3000):
        selected = np.concatenate([clusters[i] for i in rng.integers(0, len(clusters), len(clusters))])
        bias.append(float((probabilities[selected]-correct[selected]).mean()))
        brier.append(float(((probabilities[selected]-correct[selected])**2 - (raw[selected]-correct[selected])**2).mean()))
    bias_interval = np.quantile(bias, [.025, .975]).tolist()
    brier_interval = np.quantile(brier, [.025, .975]).tolist()
    probability_metrics = metrics(probabilities, correct, bins=protocol.get('reliability_bins', 10))
    unsupported_interval = wilson_interval(report['unsupported_false_acceptances'], len(unsupported))
    sites = {row['site'] for row in displayed if row['landmark_ids']}
    checks = {
        'displayed_sample_count': len(displayed) >= protocol['minimum_displayed_predictions'],
        'source_group_count': len(clusters) >= protocol['minimum_source_groups'],
        'known_site_diversity': len(sites) >= protocol['minimum_represented_known_sites'],
        'calibration_error': probability_metrics['expected_calibration_error'] <= protocol['maximum_ece'],
        'calibration_bias_uncertainty': max(abs(value) for value in bias_interval) <= protocol['maximum_absolute_calibration_bias_interval_95'],
        'raw_score_improvement': brier_interval[1] < protocol['paired_brier_vs_raw_upper_95_maximum'],
        'unsupported_false_acceptance': unsupported_interval[1] <= protocol['maximum_unsupported_false_acceptance_upper_95'],
    }
    recognition_checks = {}
    if protocol.get('unsupported_rejection_is_separate_from_probability_calibration'):
        recognition_checks['unsupported_false_acceptance'] = checks.pop('unsupported_false_acceptance')
    if protocol['paired_brier_vs_raw_upper_95_maximum'] > 0:
        checks['raw_score_noninferiority'] = checks.pop('raw_score_improvement')
    report.update(probability_metrics=probability_metrics,
                  accuracy_interval_95=wilson_interval(int(correct.sum()), len(correct)),
                  raw_score_metrics_same_subset=metrics(raw, correct),
                  calibration_bias_cluster_interval_95=bias_interval,
                  calibrated_minus_raw_brier_cluster_interval_95=brier_interval,
                  unsupported_false_acceptance_interval_95=unsupported_interval,
                  source_group_count=len(clusters), represented_known_sites=len(sites),
                  recognition_checks=recognition_checks,
                  checks=checks, failed_checks=[key for key, passed in checks.items() if not passed],
                  eligible=all(checks.values()),
                  scope='Selected source-verified web photos; confidence is conditional on acceptance and the validated probability range. Not a guarantee for arbitrary uploads.')
    if 'constant_baseline_probability' in protocol:
        report['constant_baseline_same_subset'] = metrics([protocol['constant_baseline_probability']]*len(correct),correct)
    return report
