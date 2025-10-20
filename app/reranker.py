
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from typing import List
from .config import get_settings
def pick_device():
    if torch.cuda.is_available(): return 'cuda'
    if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(): return 'mps'
    return 'cpu'
class Reranker:
    def __init__(self, model_name: str):
        self.device = pick_device()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name, trust_remote_code=True)
        self.model.to(self.device); self.model.eval()
    @torch.inference_mode()
    def score(self, query: str, candidates: List[str], batch_size: int = 16) -> List[float]:
        scores = []
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i+batch_size]
            pairs = [(query, c) for c in batch]
            inputs = self.tokenizer(pairs, padding=True, truncation=True, return_tensors='pt', max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            logits = self.model(**inputs).logits.squeeze(-1)
            probs = torch.sigmoid(logits)
            scores.extend(probs.detach().cpu().tolist())
        return scores
_reranker = None
def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        settings = get_settings()
        _reranker = Reranker(settings.reranker_model)
    return _reranker
