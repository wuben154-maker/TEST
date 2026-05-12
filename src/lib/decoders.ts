// Multi-format decoder utilities

export interface DecodeResult {
  success: boolean;
  decoded: string;
  algorithm: string;
  error?: string;
}

// Base64 decode
export function decodeBase64(input: string): DecodeResult {
  try {
    // Clean input - remove whitespace and newlines
    const cleaned = input.replace(/[\s\n\r]/g, '');
    const decoded = atob(cleaned);
    return { success: true, decoded, algorithm: 'Base64' };
  } catch {
    return { success: false, decoded: '', algorithm: 'Base64', error: 'Invalid Base64 encoding' };
  }
}

// Hex decode
export function decodeHex(input: string): DecodeResult {
  try {
    // Clean input - remove common hex prefixes and whitespace
    const cleaned = input.replace(/^0x/i, '').replace(/[\s\n\r]/g, '');
    
    if (!/^[0-9A-Fa-f]+$/.test(cleaned)) {
      return { success: false, decoded: '', algorithm: 'Hex', error: 'Invalid hex characters' };
    }
    
    if (cleaned.length % 2 !== 0) {
      return { success: false, decoded: '', algorithm: 'Hex', error: 'Hex string must have even length' };
    }
    
    let decoded = '';
    for (let i = 0; i < cleaned.length; i += 2) {
      decoded += String.fromCharCode(parseInt(cleaned.substr(i, 2), 16));
    }
    
    return { success: true, decoded, algorithm: 'Hex' };
  } catch {
    return { success: false, decoded: '', algorithm: 'Hex', error: 'Hex decode failed' };
  }
}

// URL decode
export function decodeURL(input: string): DecodeResult {
  try {
    const decoded = decodeURIComponent(input);
    return { success: true, decoded, algorithm: 'URL Encoding' };
  } catch {
    return { success: false, decoded: '', algorithm: 'URL Encoding', error: 'Invalid URL encoding' };
  }
}

// Gzip decode (browser-compatible using DecompressionStream)
export async function decodeGzip(base64Input: string): Promise<DecodeResult> {
  try {
    // First decode from base64
    const binaryString = atob(base64Input);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    
    // Check for gzip magic bytes
    if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
      return { success: false, decoded: '', algorithm: 'Gzip', error: 'Not a valid gzip stream' };
    }
    
    // Decompress using DecompressionStream API
    const stream = new Blob([bytes]).stream();
    const decompressedStream = stream.pipeThrough(new DecompressionStream('gzip'));
    const decompressedBlob = await new Response(decompressedStream).blob();
    const decoded = await decompressedBlob.text();
    
    return { success: true, decoded, algorithm: 'Gzip + Base64' };
  } catch (error) {
    return { 
      success: false, 
      decoded: '', 
      algorithm: 'Gzip', 
      error: error instanceof Error ? error.message : 'Gzip decode failed' 
    };
  }
}

// Unicode escape decode (\uXXXX)
export function decodeUnicodeEscape(input: string): DecodeResult {
  try {
    const decoded = input.replace(/\\u([0-9A-Fa-f]{4})/g, (_, hex) => 
      String.fromCharCode(parseInt(hex, 16))
    );
    return { success: true, decoded, algorithm: 'Unicode Escape' };
  } catch {
    return { success: false, decoded: '', algorithm: 'Unicode Escape', error: 'Unicode decode failed' };
  }
}

// HTML entity decode
export function decodeHTMLEntities(input: string): DecodeResult {
  try {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = input;
    const decoded = textarea.value;
    return { success: true, decoded, algorithm: 'HTML Entities' };
  } catch {
    return { success: false, decoded: '', algorithm: 'HTML Entities', error: 'HTML decode failed' };
  }
}

// ROT13 decode
export function decodeROT13(input: string): DecodeResult {
  const decoded = input.replace(/[a-zA-Z]/g, (char) => {
    const base = char <= 'Z' ? 65 : 97;
    return String.fromCharCode(((char.charCodeAt(0) - base + 13) % 26) + base);
  });
  return { success: true, decoded, algorithm: 'ROT13' };
}

// Auto-detect and decode
export async function autoDetectAndDecode(input: string): Promise<DecodeResult[]> {
  const results: DecodeResult[] = [];
  const cleaned = input.trim();
  
  // Try URL decode if contains %XX
  if (/%[0-9A-Fa-f]{2}/.test(cleaned)) {
    const urlResult = decodeURL(cleaned);
    if (urlResult.success && urlResult.decoded !== cleaned) {
      results.push(urlResult);
    }
  }
  
  // Try Base64 if matches pattern
  if (/^[A-Za-z0-9+/]+=*$/.test(cleaned.replace(/[\s\n\r]/g, '')) && cleaned.length >= 4) {
    const base64Result = decodeBase64(cleaned);
    if (base64Result.success) {
      // Check if it might be gzip (starts with H4sI in base64)
      if (cleaned.startsWith('H4sI')) {
        const gzipResult = await decodeGzip(cleaned);
        if (gzipResult.success) {
          results.push(gzipResult);
        } else {
          results.push(base64Result);
        }
      } else {
        results.push(base64Result);
      }
    }
  }
  
  // Try Hex if matches pattern
  if (/^(0x)?[0-9A-Fa-f]+$/.test(cleaned) && cleaned.length >= 2) {
    const hexResult = decodeHex(cleaned);
    if (hexResult.success) {
      results.push(hexResult);
    }
  }
  
  // Try Unicode escape if contains \uXXXX
  if (/\\u[0-9A-Fa-f]{4}/.test(cleaned)) {
    const unicodeResult = decodeUnicodeEscape(cleaned);
    if (unicodeResult.success && unicodeResult.decoded !== cleaned) {
      results.push(unicodeResult);
    }
  }
  
  // Try HTML entities if contains &XXX;
  if (/&[#\w]+;/.test(cleaned)) {
    const htmlResult = decodeHTMLEntities(cleaned);
    if (htmlResult.success && htmlResult.decoded !== cleaned) {
      results.push(htmlResult);
    }
  }
  
  return results;
}

// Pattern detection for common encodings
export function detectEncodingType(input: string): string[] {
  const types: string[] = [];
  const cleaned = input.trim();
  
  if (/%[0-9A-Fa-f]{2}/.test(cleaned)) types.push('URL');
  if (/^[A-Za-z0-9+/]+=*$/.test(cleaned.replace(/\s/g, ''))) types.push('Base64');
  if (/^(0x)?[0-9A-Fa-f]+$/.test(cleaned)) types.push('Hex');
  if (/\\u[0-9A-Fa-f]{4}/.test(cleaned)) types.push('Unicode');
  if (/&[#\w]+;/.test(cleaned)) types.push('HTML');
  if (cleaned.startsWith('H4sI')) types.push('Gzip+Base64');
  
  return types;
}
