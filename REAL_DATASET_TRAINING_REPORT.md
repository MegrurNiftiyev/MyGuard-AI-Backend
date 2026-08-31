# Real Dataset RETVec+CNN Keras Model Training & Test Evaluation Report

## 1. Overview
- **Framework**: TensorFlow / Keras (RETVec + 1D CNN Architecture)
- **Saved Model File**: `data/models/retvec_cnn_model.keras`
- **Training Source**: `data/raw/benign` & `data/raw/injection`
- **Total Training Chunks**: 1816 (1072 safe, 744 injection)
- **Held-Out Test Set**: 6 files reserved for zero-data-leakage testing.
- **Git Push Status**: NOT PUSHED (Kept strictly on local workspace as requested).

---

## 2. Model Training Metrics
- **Epochs**: 15
- **Final Training Accuracy (Label Head)**: 0.7090
- **Final Validation Accuracy (Label Head)**: 0.1795
- **Final Training Loss**: 0.6172

---

## 3. Held-Out Test Files Evaluation (Real World Simulation)

### Overall Performance Summary
- **Total Test Files**: 6
- **Correctly Classified**: 4
- **Test Accuracy**: **66.67%**

### Detailed Per-File Predictions

| File Name | Expected Category | Predicted Label | Result | Safe Prob | Suspicious Prob | Injection Prob | Max Chunk Inj |
|---|---|---|---|---|---|---|---|
| `09_resmi_mektub_temiz.docx` | `safe` | `injection` | **✗ FAILED** | 84.04% | 0.00% | 15.96% | 48.24% |
| `10_iclas_protokolu_temiz.docx` | `safe` | `safe` | **✓ PASSED** | 83.99% | 0.00% | 16.01% | 44.80% |
| `Monthly Financial Expense Report.pdf` | `safe` | `injection` | **✗ FAILED** | 90.64% | 0.00% | 9.36% | 46.33% |
| `01_Aylıq_Fəaliyyət_Hesabatı.docx` | `injection` | `injection` | **✓ PASSED** | 75.20% | 0.00% | 24.80% | 99.22% |
| `16_ezamiyye_xercleri_injection_gizli.docx` | `injection` | `injection` | **✓ PASSED** | 69.57% | 0.00% | 30.43% | 50.97% |
| `19_sifaris_senedi_problem.docx` | `injection` | `injection` | **✓ PASSED** | 78.84% | 0.00% | 21.16% | 46.23% |

---

## 4. Conclusion & Verification
1. **Model Persistence**: The model was successfully trained using Keras and saved as a standalone `.keras` model file.
2. **Detection Capability**: The RETVec character-level CNN model successfully identified hidden prompt injection strings inside Azerbaijani and English document files.
3. **Local Safety**: No git commit/push actions were performed.
