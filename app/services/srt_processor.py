import re
from typing import List, Dict, Tuple, Optional

class SubtitleBlock:
    def __init__(self, index: int, timestamp: str, text: str):
        self.index = index
        self.timestamp = timestamp.strip()
        self.text = text.strip()
        self.translated_text = ""

    def to_srt(self) -> str:
        content = self.translated_text if self.translated_text else self.text
        return f"{self.index}\n{self.timestamp}\n{content}\n"

class SRTProcessor:
    @staticmethod
    def parse_srt(content: str) -> Tuple[List[SubtitleBlock], int]:
        """
        Parses raw SRT content into SubtitleBlock list and returns total text character count.
        Handles various line ending formats (\r\n, \n, \r) and BOM characters.
        """
        # Remove UTF-8 BOM if present
        if content.startswith('\ufeff'):
            content = content[1:]
            
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Regex to match SRT blocks: Index, Timestamp, and Text until double newline
        blocks: List[SubtitleBlock] = []
        raw_blocks = re.split(r'\n\s*\n', content.strip())
        
        total_chars = 0
        current_idx = 1
        
        for raw in raw_blocks:
            lines = [l for l in raw.strip().split('\n') if l.strip()]
            if not lines:
                continue
                
            # Line 1: index (or timestamp if index missing)
            # Line 2: timestamp
            # Line 3+: text
            idx = current_idx
            ts = ""
            text_lines = []
            
            if len(lines) >= 2 and '-->' in lines[1]:
                try:
                    idx = int(re.sub(r'\D', '', lines[0]))
                except ValueError:
                    idx = current_idx
                ts = lines[1]
                text_lines = lines[2:]
            elif '-->' in lines[0]:
                idx = current_idx
                ts = lines[0]
                text_lines = lines[1:]
            else:
                continue
                
            block_text = "\n".join(text_lines).strip()
            total_chars += len(block_text)
            
            blocks.append(SubtitleBlock(index=idx, timestamp=ts, text=block_text))
            current_idx += 1
            
        return blocks, total_chars

    @staticmethod
    def chunk_blocks(blocks: List[SubtitleBlock], max_batch_size: int = 30) -> List[List[SubtitleBlock]]:
        """
        Groups subtitle blocks into batches for efficient LLM translation.
        """
        chunks = []
        for i in range(0, len(blocks), max_batch_size):
            chunks.append(blocks[i:i + max_batch_size])
        return chunks

    @staticmethod
    def create_translation_prompt(batch: List[SubtitleBlock], target_lang: str = "fa") -> str:
        """
        Prepares structured text payload for LLM with clear indexing.
        """
        lang_name = "Persian (Farsi)" if target_lang == "fa" else "English"
        
        input_lines = []
        for b in batch:
            # Replace internal newlines in single subtitle with space or || to maintain line structure
            single_line_text = b.text.replace('\n', ' ')
            input_lines.append(f"[{b.index}] {single_line_text}")
            
        payload = "\n".join(input_lines)
        return payload

    @staticmethod
    def parse_llm_response_and_update(batch: List[SubtitleBlock], response_text: str):
        """
        Parses LLM response indexed format: [1] متن ترجمه شده
        and updates the corresponding SubtitleBlock.translated_text.
        """
        # Map indices in this batch
        block_map = {b.index: b for b in batch}
        
        # Regex to find [index] translation
        pattern = re.compile(r'\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)', re.DOTALL)
        matches = pattern.findall(response_text)
        
        matched_indices = set()
        for idx_str, text in matches:
            try:
                idx = int(idx_str)
                if idx in block_map:
                    clean_text = text.strip()
                    block_map[idx].translated_text = clean_text
                    matched_indices.add(idx)
            except ValueError:
                continue
                
        # Fallback for any missed lines in the batch
        # If LLM returned raw lines without brackets matching exact count
        if len(matched_indices) < len(batch):
            lines = [l.strip() for l in response_text.strip().split('\n') if l.strip() and not l.startswith('```')]
            if len(lines) == len(batch):
                for b, l in zip(batch, lines):
                    # Remove [x] if present at beginning
                    clean = re.sub(r'^\[\d+\]\s*', '', l)
                    b.translated_text = clean
            else:
                # If still unassigned, keep original or best effort
                for b in batch:
                    if not b.translated_text:
                        b.translated_text = b.text

    @staticmethod
    def build_srt(blocks: List[SubtitleBlock]) -> str:
        """
        Reconstructs the full SRT file from all translated blocks.
        """
        output = []
        for i, block in enumerate(blocks, start=1):
            block.index = i  # ensure continuous numbering
            output.append(block.to_srt())
        return "\n".join(output).strip() + "\n"
