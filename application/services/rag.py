"""RAG (Retrieval-Augmented Generation) service for knowledge base search."""
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np
import httpx
import re
from datetime import datetime

from core.config import Config
from infrastructure.external.mc_api import MinecraftAPI
from infrastructure.external.mb_api import MineBridgeAPI


logger = logging.getLogger(__name__)


class RAGService:
    """Service for RAG index management and semantic search."""
    
    def __init__(
        self,
        config: Config,
        mc_api: MinecraftAPI,
        mb_api: MineBridgeAPI
    ):
        self.config = config
        self.mc_api = mc_api
        self.mb_api = mb_api
        
        self._rag_chunks: List[dict] = []
        self._rag_vecs: Optional[np.ndarray] = None
        self._rag_loaded = False
        self._rag_lock = asyncio.Lock()
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Request embeddings for a batch of texts via Jina API."""
        if not texts:
            return []
        
        if not self.config.JINA_API_KEY:
            logger.warning("RAG: JINA_API_KEY not configured")
            return []
        
        while True:
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(
                        "https://api.jina.ai/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {self.config.JINA_API_KEY}",
                            "Accept": "application/json",
                        },
                        json={"model": self.config.RAG_EMB_MODEL, "input": texts},
                    )
                    r.raise_for_status()
                    payload = r.json()
                    return [item["embedding"] for item in payload["data"]]
            except httpx.HTTPStatusError as e:
                body = (e.response.text or "")[:500]
                logger.exception("RAG: Jina HTTP %s, body: %s", e.response.status_code, body)
                return []
            except Exception:
                logger.exception("RAG: Jina embeddings request failed")
                return []
    
    def _read_text_file(self, p: Path) -> str:
        """Read knowledge base file and normalize text to UTF-8 with LF."""
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if raw.startswith("\ufeff"):
                raw = raw.lstrip("\ufeff")
            return raw.replace("\r\n", "\n").replace("\r", "\n")
        except Exception:
            logger.exception("RAG: failed to read %s", p)
            return ""
    
    def _clamp_priority(self, val: Optional[int]) -> int:
        """Clamp priority to valid range [0, 10]."""
        try:
            v = int(val) if val is not None else 5
        except Exception:
            v = 5
        if v < 0:
            return 0
        if v > 10:
            return 10
        return v
    
    def _extract_priority_and_strip(self, text: str) -> Tuple[int, str]:
        """Extract RAG priority from top-of-file metadata and strip it from content."""
        if not text:
            return 5, ""
        
        s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        
        first_lines = s.split("\n")[:50]
        for i, line in enumerate(first_lines):
            if not line.strip():
                continue
            m = re.match(r"(?i)^\s*(?:rag[-_ ]?priority|priority)\s*:\s*([0-9]{1,2})\s*$", line)
            if m:
                pr = self._clamp_priority(int(m.group(1)))
                rest = "\n".join(s.split("\n")[i+1:])
                return pr, rest
            break
        
        return 5, s
    
    def _split_chunks(self, text: str, size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks for vector index."""
        text = text.strip()
        if not text:
            return []
        out, i = [], 0
        while i < len(text):
            out.append(text[i:i+size])
            i += max(1, size - overlap)
        return [c for c in out if c.strip()]
    
    def _hash_str(self, s: str) -> str:
        """Simple hash for string."""
        import hashlib
        return hashlib.md5(s.encode()).hexdigest()[:16]
    
    async def _ensure_rag_index(self):
        """Load cache or rebuild index if data has changed."""
        async with self._rag_lock:
            self.config.RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)
            meta_path = self.config.RAG_INDEX_DIR / "chunks.json"
            vecs_path = self.config.RAG_INDEX_DIR / "vecs.npy"
            
            if meta_path.exists() and vecs_path.exists() and not self._rag_loaded:
                try:
                    self._rag_chunks = json.loads(meta_path.read_text(encoding="utf-8"))
                    self._rag_vecs = np.load(vecs_path)
                    self._rag_loaded = True
                    logger.info("RAG: loaded cache with %d chunks", len(self._rag_chunks))
                except Exception:
                    logger.exception("RAG: failed to load cache, rebuilding")
            
            kb_files = []
            if self.config.KB_DIR.exists():
                for p in self.config.KB_DIR.rglob("*"):
                    if p.is_file() and p.suffix.lower() in {".txt", ".md"}:
                        kb_files.append(p)
            
            known_paths = {c["file"] for c in self._rag_chunks}
            kb_paths = {str(p) for p in kb_files}
            
            need_rebuild = (not self._rag_loaded) or (known_paths != kb_paths)
            
            if not need_rebuild:
                for p in kb_files:
                    m = p.stat().st_mtime
                    if not any(c["file"] == str(p) and abs(c.get("mtime", 0.0) - m) < 1e-6 for c in self._rag_chunks):
                        need_rebuild = True
                        break
            
            if not need_rebuild:
                return
            
            logger.info("RAG: (re)building index...")
            all_chunks = []
            all_texts = []
            for p in kb_files:
                txt = self._read_text_file(p)
                pr, clean = self._extract_priority_and_strip(txt)
                parts = self._split_chunks(clean, self.config.RAG_CHUNK_SIZE, self.config.RAG_CHUNK_OVERLAP)
                m = p.stat().st_mtime
                for i, ch in enumerate(parts):
                    cid = f"{self._hash_str(str(p))}:{i}"
                    all_chunks.append({"id": cid, "file": str(p), "text": ch, "mtime": m, "priority": pr})
                    all_texts.append(ch)
            
            vecs = []
            for i in range(0, len(all_texts), self.config.RAG_EMB_BATCH):
                batch = all_texts[i:i+self.config.RAG_EMB_BATCH]
                vecs.extend(await self._embed_batch(batch))
            
            if vecs:
                V = np.array(vecs, dtype="float32")
                norms = np.linalg.norm(V, axis=1, keepdims=True)
                norms[norms == 0.0] = 1.0
                V /= norms
                self._rag_chunks = all_chunks
                self._rag_vecs = V
                meta_path.write_text(json.dumps(self._rag_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
                np.save(vecs_path, self._rag_vecs)
                self._rag_loaded = True
                logger.info("RAG: built %d chunks from %d files", len(self._rag_chunks), len(kb_files))
            else:
                self._rag_chunks, self._rag_vecs, self._rag_loaded = [], None, True
                logger.warning("RAG: no chunks produced (empty kb?)")
    
    async def search(self, query: str) -> List[Tuple[dict, float]]:
        """Return top-k most relevant chunks from knowledge base."""
        await self._ensure_rag_index()
        
        if self._rag_vecs is None or len(self._rag_chunks) == 0:
            return []
        
        embeddings = await self._embed_batch([query])
        if not embeddings:
            return []
        
        q_emb = embeddings[0]
        q = np.array([q_emb], dtype="float32")
        q /= max(np.linalg.norm(q), 1e-12)
        sims = (self._rag_vecs @ q.T).reshape(-1)
        
        weights = np.array([
            max(0.1, (float((c.get("priority", 5) or 5)) / 5.0))
            for c in self._rag_chunks
        ], dtype="float32")
        adj = sims * weights
        top_idx = np.argsort(-adj)[:self.config.RAG_TOP_K]
        return [(self._rag_chunks[i], float(adj[i])) for i in top_idx]
    
    async def build_full_context(
        self,
        prompt: str,
        user_id: Optional[int] = None
    ) -> str:
        """Build dynamic context from server status, player data, and RAG chunks."""
        sections: List[str] = []
        
        status_task = asyncio.create_task(self.mc_api.fetch_status())
        search_task = asyncio.create_task(self.search(prompt))
        player_task = asyncio.create_task(self.mb_api.fetch_player_by_id(str(user_id))) if user_id else None
        
        # Get user psevdo if available
        from infrastructure.repositories.psevdos import PsevdoRepository
        psevdo_repo = PsevdoRepository(self.config.PSEVDO_FILE)
        psevdo = psevdo_repo.get_psevdo(user_id) if user_id else None
        if psevdo:
            sections.append(f"Обращайся к игроку: '<b>{psevdo}</b>'\n")
        
        # Dynamic server context
        try:
            payload = await status_task
            server_ctx = self.mc_api.format_status_text(payload)
            if server_ctx:
                sections.append(f"Пиши про статус, только когда просят\n{server_ctx}\n")
        except Exception:
            logger.exception("RAG: failed to fetch server status")
        
        # Dynamic player context
        if user_id and player_task:
            try:
                player_info = await player_task
                if player_info:
                    sections.append(f"Игрок (из MineBridge API):\nИспользуй данные аккаунта, только когда просят\n{json.dumps(player_info, ensure_ascii=False)}\n")
            except Exception:
                logger.exception("RAG: failed to fetch player info")
        
        sections.append(f"Текущая дата: {datetime.now()}")
        
        # Knowledge base via semantic search
        results = await search_task
        if results:
            kb_parts: List[str] = []
            for ch, _sc in results:
                snippet = (ch.get("text") or "").strip()
                if snippet:
                    kb_parts.append(snippet)
            if kb_parts:
                sections.append("\n".join(kb_parts))
        
        return "\n\n".join([s for s in sections if s])
    
    def get_chunks(self) -> List[dict]:
        """Get current RAG chunks."""
        return self._rag_chunks
    
    def get_loaded(self) -> bool:
        """Check if RAG index is loaded."""
        return self._rag_loaded
    
    async def reset_index(self):
        """Force rebuild of RAG index."""
        async with self._rag_lock:
            self._rag_loaded = False
            self._rag_chunks = []
            self._rag_vecs = None
        await self._ensure_rag_index()
