"""File Parser Module - Multi-format file parsing with multi-language support.

Supports parsing various file types including:
- Text files (TXT, LOG, MD, etc.)
- Code files (Python, JavaScript, etc.)
- Binary files (PE, ELF, PCAP)
- Documents (PDF, Word)
- Archives (ZIP, 7Z, RAR)
- Images (with OCR)
"""

import hashlib
import json
import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class FileInfo:
    """Uploaded file information."""
    filename: str
    content_type: str
    size: int
    content: bytes | str | None = None
    hash_md5: str = ""
    hash_sha256: str = ""
    parsed_content: str = ""
    
    def compute_hashes(self):
        """Compute file hashes (MD5 and SHA256)."""
        if self.content:
            data = self.content if isinstance(self.content, bytes) else self.content.encode()
            self.hash_md5 = hashlib.md5(data).hexdigest()
            self.hash_sha256 = hashlib.sha256(data).hexdigest()


# InputType is imported from intent_models when needed (see detect_input_type)


class FileParser:
    """File parser - supports multiple file types with multi-language support."""
    
    # Supported MIME types
    TEXT_TYPES = {
        "text/plain", "text/html", "text/css", "text/javascript",
        "text/csv", "text/xml", "text/markdown",
        "application/json", "application/xml", "application/javascript",
    }
    
    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
        ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".ps1", ".sql",
    }
    
    LOG_PATTERNS = [
        r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}",  # Timestamp
        r"\[(INFO|WARN|ERROR|DEBUG)\]",  # Log level
        r"^\w+\s+\d+\s+\d+:\d+:\d+",  # Syslog format
    ]
    
    EMAIL_PATTERNS = [
        r"^From:\s*.+",
        r"^To:\s*.+",
        r"^Subject:\s*.+",
        r"^Received:\s*.+",
        r"^DKIM-Signature:",
    ]
    
    def __init__(self, language: str = "en"):
        """Initialize file parser.
        
        Args:
            language: Language code for output messages (default: 'en')
        """
        self.language = language
        self._magic = None
        try:
            import magic
            self._magic = magic.Magic(mime=True)
            logger.info("File type detection enabled (python-magic)")
        except ImportError:
            logger.warning("python-magic not available, using fallback detection")
        except Exception as e:
            logger.warning("Failed to initialize magic library", error=str(e))
    
    def _label(self, key: str) -> str:
        """Get localized label for file parsing messages.
        
        Args:
            key: Label key (e.g., 'file_binary')
        
        Returns:
            Localized label string
        """
        from app.parsers.labels import get_file_parsing_label
        return get_file_parsing_label(key, self.language)
    
    def _format_error_message(self, title_key: str, file_info: FileInfo, 
                             error: str = None, install_note_key: str = None) -> str:
        """Format error message with consistent structure.
        
        Args:
            title_key: Label key for error title
            file_info: File information
            error: Optional error message
            install_note_key: Optional label key for installation note
        
        Returns:
            Formatted error message string
        """
        parts = [f"[{self._label(title_key)}: {file_info.filename}]"]
        parts.append(f"{self._label('file_filename')}: {file_info.filename}")
        if file_info.size:
            parts.append(f"{self._label('file_size')}: {file_info.size} {self._label('file_bytes')}")
        if error:
            parts.append(f"{self._label('file_error')}: {error}")
        if install_note_key:
            parts.append(self._label(install_note_key))
        return "\n".join(parts)
    
    def _detect_file_type(self, file_info: FileInfo) -> str:
        """Detect file type, prioritize magic number detection, fallback to extension.
        
        Returns:
            MIME type string, returns original content_type if detection fails
        """
        # Prioritize magic number detection (more accurate, can detect file type spoofing)
        if self._magic and file_info.content:
            try:
                if isinstance(file_info.content, bytes):
                    # Use first 8192 bytes for detection (magic number usually in file header)
                    sample = file_info.content[:8192]
                    detected_type = self._magic.from_buffer(sample)
                    if detected_type:
                        logger.debug("File type detected by magic", 
                                   filename=file_info.filename,
                                   detected=detected_type,
                                   original=file_info.content_type)
                        return detected_type
                elif isinstance(file_info.content, str):
                    # String content, convert to bytes
                    sample = file_info.content.encode('utf-8', errors='ignore')[:8192]
                    detected_type = self._magic.from_buffer(sample)
                    if detected_type:
                        return detected_type
            except Exception as e:
                logger.debug("Magic detection failed", filename=file_info.filename, error=str(e))
        
        # Fallback: use original content_type or extension inference
        if file_info.content_type:
            return file_info.content_type
        
        # Final attempt: infer from extension
        import mimetypes
        guessed_type, _ = mimetypes.guess_type(file_info.filename)
        return guessed_type or "application/octet-stream"
    
    def parse_file(self, file_info: FileInfo) -> str:
        """Parse file content."""
        # Use enhanced file type detection
        detected_type = self._detect_file_type(file_info)
        content_type = detected_type.lower()
        filename = file_info.filename.lower()
        
        # Check file size, apply smart sampling strategy
        file_size = file_info.size or 0
        if file_size > 0:
            sampled_content = self._smart_sample(file_info, file_size)
            if sampled_content:
                return sampled_content
        
        # Text types (use detected type)
        if content_type in self.TEXT_TYPES or filename.endswith((".txt", ".log", ".md")):
            return self._parse_text(file_info)
        
        # Code files
        for ext in self.CODE_EXTENSIONS:
            if filename.endswith(ext):
                return self._parse_code(file_info)
        
        # JSON
        if filename.endswith(".json") or content_type == "application/json":
            return self._parse_json(file_info)
        
        # Email
        if filename.endswith((".eml", ".msg")):
            return self._parse_email(file_info)
        
        # Advanced file type parsing
        # PCAP network packets
        if filename.endswith(".pcap") or content_type == "application/vnd.tcpdump.pcap":
            return self._parse_pcap(file_info)
        
        # PE executable files
        if filename.endswith((".exe", ".dll", ".sys")) or "pe" in content_type or "executable" in content_type:
            return self._parse_pe(file_info)
        
        # ELF executable files
        if filename.endswith((".elf", ".so", ".bin")) or "elf" in content_type:
            return self._parse_elf(file_info)
        
        # Archive files
        if filename.endswith((".zip", ".7z", ".rar", ".tar", ".gz", ".bz2")):
            return self._parse_archive(file_info)
        
        # PDF documents
        if filename.endswith(".pdf") or content_type == "application/pdf":
            return self._parse_pdf(file_info)
        
        # Word documents
        if filename.endswith((".docx", ".doc")) or "msword" in content_type or "wordprocessingml" in content_type:
            return self._parse_docx(file_info)
        
        # Image OCR
        if content_type.startswith("image/"):
            return self._parse_image_ocr(file_info)
        
        # Binary files - return metadata
        return self._parse_binary_metadata(file_info)
    
    def _parse_text(self, file_info: FileInfo) -> str:
        """Parse text file."""
        if isinstance(file_info.content, bytes):
            try:
                return file_info.content.decode("utf-8")
            except UnicodeDecodeError:
                return file_info.content.decode("latin-1", errors="replace")
        return str(file_info.content or "")
    
    def _parse_code(self, file_info: FileInfo) -> str:
        """Parse code file."""
        content = self._parse_text(file_info)
        ext = file_info.filename.split(".")[-1]
        return f"```{ext}\n{content}\n```"
    
    def _parse_json(self, file_info: FileInfo) -> str:
        """Parse JSON file."""
        content = self._parse_text(file_info)
        try:
            data = json.loads(content)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            return content
    
    def _parse_email(self, file_info: FileInfo) -> str:
        """Parse email file."""
        content = self._parse_text(file_info)
        # Extract key email headers
        headers = []
        for line in content.split("\n")[:50]:
            if any(re.match(p, line, re.IGNORECASE) for p in self.EMAIL_PATTERNS):
                headers.append(line)
        
        if headers:
            parts = [
                f"{self._label('file_email_headers')}:",
                "\n".join(headers[:20]),
                "",
                content[:2000]
            ]
            return "\n".join(parts)
        return content
    
    def _parse_binary_metadata(self, file_info: FileInfo) -> str:
        """Parse binary file metadata."""
        file_info.compute_hashes()
        parts = [
            f"[{self._label('file_binary')}]",
            f"{self._label('file_filename')}: {file_info.filename}",
            f"{self._label('file_type')}: {file_info.content_type}",
            f"{self._label('file_size')}: {file_info.size} {self._label('file_bytes')}",
            f"MD5: {file_info.hash_md5}",
            f"SHA256: {file_info.hash_sha256}"
        ]
        return "\n".join(parts)
    
    def _parse_pcap(self, file_info: FileInfo) -> str:
        """Parse PCAP network packet file."""
        try:
            from scapy.all import DNS, IP, TCP, UDP, rdpcap
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            # Limit packet reading to avoid memory issues
            packets = rdpcap(content[:10*1024*1024])  # Max 10MB
            total_packets = len(packets)
            
            parts = [f"[{self._label('file_pcap_analysis')}: {file_info.filename}]"]
            parts.append(f"{self._label('file_pcap_total_packets')}: {total_packets}")
            
            # Collect statistics
            ip_count = tcp_count = udp_count = dns_count = 0
            src_ips = set()
            dst_ips = set()
            
            # Analyze first 100 packets (avoid long processing time)
            sample_size = min(100, total_packets)
            for pkt in packets[:sample_size]:
                if IP in pkt:
                    ip_count += 1
                    src_ips.add(pkt[IP].src)
                    dst_ips.add(pkt[IP].dst)
                    if TCP in pkt:
                        tcp_count += 1
                    elif UDP in pkt:
                        udp_count += 1
                        if DNS in pkt:
                            dns_count += 1
            
            # Format statistics
            parts.append(f"\n[{self._label('file_pcap_statistics')}]")
            parts.append(f"{self._label('file_pcap_ip_packets')}: {ip_count}")
            parts.append(f"{self._label('file_pcap_tcp_packets')}: {tcp_count}")
            parts.append(f"{self._label('file_pcap_udp_packets')}: {udp_count}")
            parts.append(f"{self._label('file_pcap_dns_packets')}: {dns_count}")
            parts.append(f"{self._label('file_pcap_src_ip_count')}: {len(src_ips)}")
            parts.append(f"{self._label('file_pcap_dst_ip_count')}: {len(dst_ips)}")
            
            if src_ips:
                parts.append(f"\n[{self._label('file_pcap_src_ips')}]")
                parts.extend(list(src_ips)[:20])
            
            if dst_ips:
                parts.append(f"\n[{self._label('file_pcap_dst_ips')}]")
                parts.extend(list(dst_ips)[:20])
            
            if total_packets > sample_size:
                note = self._label('file_pcap_sample_note').format(
                    sample_size=sample_size, total=total_packets
                )
                parts.append(f"\n{note}")
            
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_pcap_requires_lib', file_info,
                install_note_key='file_pcap_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse PCAP", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_pcap_parse_failed', file_info, error=str(e))
    
    def _parse_pe(self, file_info: FileInfo) -> str:
        """Parse PE (Portable Executable) file."""
        try:
            import pefile
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            pe = pefile.PE(data=content)
            
            parts = [f"[{self._label('file_pe_analysis')}: {file_info.filename}]"]
            parts.append(f"{self._label('file_pe_architecture')}: {pe.FILE_HEADER.Machine}")
            parts.append(f"{self._label('file_pe_timestamp')}: {pe.FILE_HEADER.TimeDateStamp}")
            
            # Import table
            if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
                parts.append(f"\n[{self._label('file_pe_imported_dlls')}]")
                imports = [
                    entry.dll.decode('utf-8', errors='ignore')
                    for entry in pe.DIRECTORY_ENTRY_IMPORT
                ]
                parts.extend(imports[:30])
            
            # Export table
            if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
                parts.append(f"\n[{self._label('file_pe_exported_functions')}]")
                exports = [
                    exp.name.decode('utf-8', errors='ignore')
                    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols
                    if exp.name
                ]
                parts.extend(exports[:30])
            
            # Section information
            parts.append(f"\n[{self._label('file_pe_sections')}]")
            for section in pe.sections:
                name = section.Name.decode('utf-8', errors='ignore').rstrip('\x00')
                parts.append(f"  {name}: {section.Misc_VirtualSize} {self._label('file_bytes')}")
            
            pe.close()
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_pe_requires_lib', file_info,
                install_note_key='file_pe_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse PE", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_pe_parse_failed', file_info, error=str(e))
    
    def _parse_elf(self, file_info: FileInfo) -> str:
        """Parse ELF executable file."""
        try:
            from io import BytesIO

            from elftools.elf.elffile import ELFFile
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            elf_file = ELFFile(BytesIO(content))
            
            parts = [f"[{self._label('file_elf_analysis')}: {file_info.filename}]"]
            parts.append(f"{self._label('file_pe_architecture')}: {elf_file.get_machine_arch()}")
            parts.append(f"{self._label('file_type')}: {elf_file.header['e_type']}")
            
            # Section information
            parts.append(f"\n[{self._label('file_elf_sections')}]")
            for section in elf_file.iter_sections():
                parts.append(f"  {section.name}: {section['sh_size']} {self._label('file_bytes')}")
            
            # Symbol table
            try:
                symtab = elf_file.get_section_by_name('.symtab')
                if symtab:
                    parts.append(f"\n[{self._label('file_elf_symbol_table')}]")
                    symbols = [
                        symbol.name for symbol in symtab.iter_symbols()
                        if symbol.name
                    ]
                    parts.extend(symbols[:30])
            except Exception:
                pass
            
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_elf_requires_lib', file_info,
                install_note_key='file_elf_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse ELF", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_elf_parse_failed', file_info, error=str(e))
    
    def _parse_archive(self, file_info: FileInfo) -> str:
        """Parse archive file (ZIP, 7Z, RAR, etc.)."""
        parts = [f"[{self._label('file_archive_analysis')}: {file_info.filename}]"]
        parts.append(f"{self._label('file_size')}: {file_info.size} {self._label('file_bytes')}")
        
        filename = file_info.filename.lower()
        
        try:
            if filename.endswith(".zip"):
                import zipfile
                from io import BytesIO
                
                content = file_info.content
                if isinstance(content, str):
                    content = content.encode('latin-1', errors='ignore')
                
                with zipfile.ZipFile(BytesIO(content)) as zf:
                    file_list = zf.namelist()
                    parts.append(f"{self._label('file_archive_file_count')}: {len(file_list)}")
                    parts.append(f"\n[{self._label('file_archive_file_list')}]")
                    for name in file_list[:50]:  # Max 50 files
                        info = zf.getinfo(name)
                        parts.append(f"  {name} ({info.file_size} {self._label('file_bytes')})")
                    if len(file_list) > 50:
                        more_count = len(file_list) - 50
                        note = self._label('file_archive_more_files').format(count=more_count)
                        parts.append(f"  {note}")
            
            elif filename.endswith(".7z"):
                from io import BytesIO

                import py7zr
                
                content = file_info.content
                if isinstance(content, str):
                    content = content.encode('latin-1', errors='ignore')
                
                with py7zr.SevenZipFile(BytesIO(content), mode='r') as archive:
                    files = archive.getnames()
                    parts.append(f"{self._label('file_archive_file_count')}: {len(files)}")
                    parts.append(f"\n[{self._label('file_archive_file_list')}]")
                    parts.extend(files[:50])
                    if len(files) > 50:
                        more_count = len(files) - 50
                        note = self._label('file_archive_more_files').format(count=more_count)
                        parts.append(f"  {note}")
            
            elif filename.endswith(".rar"):
                from io import BytesIO

                import rarfile
                
                content = file_info.content
                if isinstance(content, str):
                    content = content.encode('latin-1', errors='ignore')
                
                with rarfile.RarFile(BytesIO(content)) as rf:
                    file_list = rf.namelist()
                    parts.append(f"{self._label('file_archive_file_count')}: {len(file_list)}")
                    parts.append(f"\n[{self._label('file_archive_file_list')}]")
                    for name in file_list[:50]:
                        info = rf.getinfo(name)
                        parts.append(f"  {name} ({info.file_size} {self._label('file_bytes')})")
                    if len(file_list) > 50:
                        more_count = len(file_list) - 50
                        note = self._label('file_archive_more_files').format(count=more_count)
                        parts.append(f"  {note}")
            
            else:
                parts.append(self._label('file_archive_unsupported_format'))
            
            return "\n".join(parts)
        except ImportError as e:
            return self._format_error_message(
                'file_archive_requires_lib', file_info,
                error=str(e), install_note_key='file_archive_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse archive", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_archive_parse_failed', file_info, error=str(e))
    
    def _parse_pdf(self, file_info: FileInfo) -> str:
        """Parse PDF document."""
        try:
            from io import BytesIO

            from PyPDF2 import PdfReader
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            pdf = PdfReader(BytesIO(content))
            
            parts = [f"[{self._label('file_pdf_analysis')}: {file_info.filename}]"]
            parts.append(f"{self._label('file_pdf_page_count')}: {len(pdf.pages)}")
            
            # Extract metadata
            if pdf.metadata:
                parts.append(f"\n[{self._label('file_pdf_metadata')}]")
                for key, value in pdf.metadata.items():
                    parts.append(f"  {key}: {value}")
            
            # Extract text from first 3 pages
            parts.append(f"\n[{self._label('file_pdf_text_preview')}]")
            for i, page in enumerate(pdf.pages[:3]):
                text = page.extract_text()
                if text:
                    page_label = self._label('file_pdf_page_n').format(n=i+1)
                    parts.append(f"\n[{page_label}]")
                    parts.append(text[:1000])  # Max 1000 chars per page
                    if len(text) > 1000:
                        parts.append(self._label('file_pdf_content_truncated'))
            
            if len(pdf.pages) > 3:
                note = self._label('file_pdf_page_limit_note').format(total=len(pdf.pages))
                parts.append(f"\n{note}")
            
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_pdf_requires_lib', file_info,
                install_note_key='file_pdf_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse PDF", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_pdf_parse_failed', file_info, error=str(e))
    
    def _parse_docx(self, file_info: FileInfo) -> str:
        """Parse Word document."""
        try:
            from io import BytesIO

            from docx import Document
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            doc = Document(BytesIO(content))
            
            parts = [f"[{self._label('file_docx_analysis')}: {file_info.filename}]"]
            
            # Extract paragraphs
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            
            parts.append(f"{self._label('file_docx_paragraph_count')}: {len(paragraphs)}")
            parts.append(f"\n[{self._label('file_docx_content_preview')}]")
            parts.extend(paragraphs[:50])  # Max 50 paragraphs
            
            if len(paragraphs) > 50:
                note = self._label('file_docx_paragraph_limit_note').format(total=len(paragraphs))
                parts.append(f"\n{note}")
            
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_docx_requires_lib', file_info,
                install_note_key='file_docx_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse DOCX", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_docx_parse_failed', file_info, error=str(e))
    
    def _parse_image_ocr(self, file_info: FileInfo) -> str:
        """Extract text from image using OCR."""
        try:
            from io import BytesIO

            import pytesseract
            from PIL import Image
            
            if not file_info.content:
                return self._parse_binary_metadata(file_info)
            
            content = file_info.content
            if isinstance(content, str):
                content = content.encode('latin-1', errors='ignore')
            
            image = Image.open(BytesIO(content))
            
            parts = [f"[{self._label('file_image_ocr_analysis')}: {file_info.filename}]"]
            parts.append(f"{self._label('file_image_dimensions')}: {image.size[0]}x{image.size[1]}")
            parts.append(f"{self._label('file_image_mode')}: {image.mode}")
            
            # Extract text using OCR
            try:
                text = pytesseract.image_to_string(image, lang='chi_sim+eng')  # Support Chinese and English
                if text.strip():
                    parts.append(f"\n[{self._label('file_image_extracted_text')}]")
                    parts.append(text[:5000])  # Max 5000 chars
                    if len(text) > 5000:
                        parts.append(f"\n{self._label('file_pdf_content_truncated')}")
                else:
                    parts.append(f"\n{self._label('file_image_no_text')}")
            except Exception as ocr_error:
                error_msg = self._label('file_image_ocr_failed').format(error=str(ocr_error))
                parts.append(f"\n{error_msg}")
            
            return "\n".join(parts)
        except ImportError:
            return self._format_error_message(
                'file_image_requires_lib', file_info,
                install_note_key='file_image_install_note'
            )
        except Exception as e:
            logger.error("Failed to parse image with OCR", filename=file_info.filename, error=str(e))
            return self._format_error_message('file_image_parse_failed', file_info, error=str(e))
    
    def _smart_sample(self, file_info: FileInfo, file_size: int) -> str | None:
        """Smart sampling strategy based on file size.
        
        Args:
            file_info: File information
            file_size: File size in bytes
        
        Returns:
            Sampled content string, or None if sampling is not needed
        """
        # File size thresholds (in bytes)
        MB = 1024 * 1024
        SIZE_1MB = 1 * MB
        SIZE_10MB = 10 * MB
        SIZE_100MB = 100 * MB
        
        # < 1MB: Full parsing (no sampling)
        if file_size < SIZE_1MB:
            return None
        
        # Get file content
        if not file_info.content:
            return None
        
        # Convert to string
        if isinstance(file_info.content, bytes):
            try:
                content = file_info.content.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file, return metadata only
                file_info.compute_hashes()
                parts = [
                    f"[{self._label('file_large_metadata_only')}: {file_info.filename}]",
                    f"{self._label('file_filename')}: {file_info.filename}",
                    f"{self._label('file_type')}: {file_info.content_type}",
                    f"{self._label('file_size')}: {file_size:,} {self._label('file_bytes')} ({file_size / MB:.2f} MB)",
                    f"MD5: {file_info.hash_md5}",
                    f"SHA256: {file_info.hash_sha256}",
                    "",
                    self._label('file_large_note')
                ]
                return "\n".join(parts)
        else:
            content = str(file_info.content)
        
        lines = content.split("\n")
        total_lines = len(lines)
        
        # 1-10MB: Smart sampling (head + middle + tail)
        if SIZE_1MB <= file_size < SIZE_10MB:
            # Sampling strategy: first 500 lines + middle key section + last 500 lines
            head_lines = 500
            tail_lines = 500
            middle_sample_size = 200  # Middle sample line count
            
            sampled = []
            title = self._label('file_sampling_analysis').format(
                size=f"{file_size / MB:.2f}",
                lines=f"{total_lines:,}"
            )
            sampled.append(f"[{title}]")
            sampled.append("=" * 60)
            
            # Header
            if total_lines > 0:
                header_label = self._label('file_sampling_header').format(n=min(head_lines, total_lines))
                sampled.append(f"[{header_label}]")
                sampled.extend(lines[:head_lines])
            
            # Middle sampling (if file is large enough)
            if total_lines > (head_lines + tail_lines + middle_sample_size):
                middle_start = total_lines // 2 - middle_sample_size // 2
                middle_label = self._label('file_sampling_middle').format(
                    start=f"{middle_start:,}",
                    end=f"{middle_start + middle_sample_size:,}"
                )
                sampled.append(f"\n[{middle_label}]")
                sampled.extend(lines[middle_start:middle_start + middle_sample_size])
            
            # Tail
            if total_lines > head_lines:
                tail_label = self._label('file_sampling_tail').format(
                    n=min(tail_lines, total_lines - head_lines)
                )
                sampled.append(f"\n[{tail_label}]")
                sampled.extend(lines[-tail_lines:])
            
            sampled.append("=" * 60)
            note = self._label('file_sampling_note').format(lines=f"{total_lines:,}")
            sampled.append(f"\n{note}")
            
            return "\n".join(sampled)
        
        # 10-100MB: Structure analysis + chunked reading
        elif SIZE_10MB <= file_size < SIZE_100MB:
            # Return only structure info and head/tail preview
            head_lines = 100
            tail_lines = 100
            
            sampled = []
            title = self._label('file_structure_analysis').format(
                size=f"{file_size / MB:.2f}",
                lines=f"{total_lines:,}"
            )
            sampled.append(f"[{title}]")
            sampled.append("=" * 60)
            
            # File statistics
            sampled.append(f"{self._label('file_filename')}: {file_info.filename}")
            sampled.append(f"{self._label('file_type')}: {file_info.content_type}")
            sampled.append(f"{self._label('file_size')}: {file_size:,} {self._label('file_bytes')} ({file_size / MB:.2f} MB)")
            sampled.append(f"Total lines: {total_lines:,}")
            
            # Detect file type
            detected_type = self.detect_input_type(content[:10000])  # Use first 10KB for detection
            sampled.append(f"{self._label('file_structure_detected_type')}: {detected_type.value}")
            
            # Header preview
            if total_lines > 0:
                header_label = self._label('file_structure_header_preview').format(
                    n=min(head_lines, total_lines)
                )
                sampled.append(f"\n[{header_label}]")
                sampled.extend(lines[:head_lines])
            
            # Tail preview
            if total_lines > head_lines:
                tail_label = self._label('file_structure_tail_preview').format(
                    n=min(tail_lines, total_lines - head_lines)
                )
                sampled.append(f"\n[{tail_label}]")
                sampled.extend(lines[-tail_lines:])
            
            sampled.append("=" * 60)
            sampled.append(f"\n{self._label('file_structure_note')}")
            sampled.append(self._label('file_structure_suggestion'))
            
            return "\n".join(sampled)
        
        # > 100MB: Metadata only + user confirmation
        else:
            file_info.compute_hashes()
            parts = [
                f"[{self._label('file_huge_metadata_only')}: {file_info.filename}]",
                f"{self._label('file_filename')}: {file_info.filename}",
                f"{self._label('file_type')}: {file_info.content_type}",
                f"{self._label('file_size')}: {file_size:,} {self._label('file_bytes')} ({file_size / MB:.2f} MB)",
                f"MD5: {file_info.hash_md5}",
                f"SHA256: {file_info.hash_sha256}",
                "",
                self._label('file_huge_note'),
                self._label('file_huge_suggestions'),
                f"1. {self._label('file_huge_suggestion_1')}",
                f"2. {self._label('file_huge_suggestion_2')}",
                f"3. {self._label('file_huge_suggestion_3')}"
            ]
            return "\n".join(parts)
    
    def detect_input_type(self, content: str) -> "InputType":
        """Detect input content type.
        
        Args:
            content: Content string to analyze
        
        Returns:
            Detected InputType enum value
        """
        # Import InputType from intent_models to avoid circular dependency
        from app.middleware.intent_models import InputType

        # Email detection
        email_score = sum(1 for p in self.EMAIL_PATTERNS if re.search(p, content, re.MULTILINE | re.IGNORECASE))
        if email_score >= 2:
            return InputType.EMAIL
        
        # Log detection
        log_score = sum(1 for p in self.LOG_PATTERNS if re.search(p, content, re.MULTILINE))
        if log_score >= 2:
            return InputType.LOG
        
        # Code detection
        code_patterns = [
            r"^import\s+\w+",
            r"^from\s+\w+\s+import",
            r"^function\s+\w+",
            r"^def\s+\w+",
            r"^class\s+\w+",
        ]
        code_score = sum(1 for p in code_patterns if re.search(p, content, re.MULTILINE))
        if code_score >= 1:
            return InputType.CODE
        
        return InputType.TEXT
