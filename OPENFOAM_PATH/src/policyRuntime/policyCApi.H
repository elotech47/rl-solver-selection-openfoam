/**
 * @file policyCApi.H
 * C ABI bridge — LibTorch stays in an ABI=0 TU; OpenFOAM callers stay ABI=1.
 */

#ifndef policyCApi_H
#define policyCApi_H

#ifdef __cplusplus
extern "C" {
#endif

/** Load TorchScript module. Returns nullptr on failure. */
void* ofRlPolicy_load(const char* modelPath);

/** Free handle from ofRlPolicy_load. */
void ofRlPolicy_free(void* handle);

/**
 * Batch infer.
 * feats: row-major [n * 19], already normalized.
 * flags/conf/pQss out length n.
 * Action 0=CVODE, 1=QSS; conf gate applied.
 * pQss = softmax P(QSS) before conf gate (for |p-0.5| analysis).
 */
void ofRlPolicy_inferBatch
(
    void* handle,
    const double* feats,
    int n,
    double confidenceThreshold,
    int* flags,
    double* confidences,
    double* pQss
);

#ifdef __cplusplus
} // extern "C"
#endif

#endif
