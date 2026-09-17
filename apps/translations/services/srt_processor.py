import re
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class SRTBlock:
    index: int
    timing: str
    text: str

class SRTProcessor:
    """Robust parser, character counter, chunker and reconstructor for SRT subtitles."""
    
    # Regex to capture individual subtitle blocks: Index, Timing (00:00:00,000 --> 00:00:00,000), and Text
    SRT_REGEX = re.compile(
        r'(?:^|\r?\n)(\d+)\r?\n'
        r'(\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3})\r?\n'
        r'((?:(?!\r?\n\r?\n|\r?\n\d+\r?\n\d{2}:\d{2}:\d{2}).)+)',
        re.DOTALL
    )

    @classmethod
    def parse_srt(cls, content: str) -> Tuple[List[SRTBlock], int]:
        """
        Parse raw SRT content string into a list of SRTBlock objects.
        Returns (blocks, total_character_count).
        """
        # Normalize newlines and clean UTF-8 BOM if present
        clean_content = content.replace('\ufeff', '').strip()
        matches = cls.SRT_REGEX.findall(clean_content)
        
        blocks: List[SRTBlock] = []
        total_chars = 0

        for match in matches:
            idx = int(match[0])
            timing = match[1].strip()
            # Clean up multi-line text and strip whitespace
            text = match[2].strip()
            blocks.append(SRTBlock(index=idx, timing=timing, text=text))
            total_chars += len(text)

        # Fallback manual line-by-line parsing if regex found no blocks
        if not blocks and clean_content:
            parts = re.split(r'\r?\n\r?\n+', clean_content)
            for part in parts:
                lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
                if len(lines) >= 3 and lines[0].isdigit() and '-->' in lines[1]:
                    idx = int(lines[0])
                    timing = lines[1]
                    text = "\n".join(lines[2:])
                    blocks.append(SRTBlock(index=idx, timing=timing, text=text))
                    total_chars += len(text)

        return blocks, total_chars

    @classmethod
    def chunk_blocks(cls, blocks: List[SRTBlock], max_chars_per_chunk: int = 38000) -> List[List[SRTBlock]]:
        """
        Group subtitle blocks into chunks suitable for LLM translation without exceeding token/char bounds.
        Leverages Gemini's 64k output context window for coherent, large-chunk narrative continuity.
        """
        chunks: List[List[SRTBlock]] = []
        current_chunk: List[SRTBlock] = []
        current_chars = 0

        for block in blocks:
            block_len = len(block.text)
            if current_chunk and (current_chars + block_len > max_chars_per_chunk):
                chunks.append(current_chunk)
                current_chunk = [block]
                current_chars = block_len
            else:
                current_chunk.append(block)
                current_chars += block_len

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    @classmethod
    def format_chunk_for_llm(cls, chunk: List[SRTBlock]) -> str:
        """Format a list of blocks for LLM prompt with clear delimiter IDs."""
        formatted_lines = []
        for block in chunk:
            # Flatten multi-line text with explicit separator if needed
            single_line_text = block.text.replace("\n", " [BR] ")
            formatted_lines.append(f"[{block.index}] {single_line_text}")
        return "\n".join(formatted_lines)

    @classmethod
    def parse_llm_response(cls, llm_response: str, chunk: List[SRTBlock]) -> List[SRTBlock]:
        """
        Parse translated text lines returned from LLM and map them back to original SRTBlock timings.
        """
        translated_map = {}
        lines = [line.strip() for line in llm_response.splitlines() if line.strip()]

        for line in lines:
            # Match pattern like [1] or 1. or 1:
            match = re.match(r'^\[?(\d+)\]?[\.\:\-\s]+(.+)$', line)
            if match:
                idx = int(match.group(1))
                text = match.group(2).replace("[BR]", "\n").strip()
                translated_map[idx] = text

        result_blocks = []
        for orig_block in chunk:
            translated_text = translated_map.get(orig_block.index)
            if not translated_text:
                # Fallback to original text if LLM dropped the line
                translated_text = orig_block.text
            result_blocks.append(SRTBlock(
                index=orig_block.index,
                timing=orig_block.timing,
                text=translated_text
            ))

        return result_blocks

    @classmethod
    def reconstruct_srt(cls, blocks: List[SRTBlock]) -> str:
        """Reconstruct valid SRT formatted string from a list of SRTBlock objects."""
        output_parts = []
        for i, block in enumerate(blocks, start=1):
            output_parts.append(f"{i}\n{block.timing}\n{block.text}\n")
        return "\n".join(output_parts).strip() + "\n"
