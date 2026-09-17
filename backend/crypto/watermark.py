"""
File Overview:
Handles the dynamic, server-side generation of forensic watermarks for PDF documents.

Important Functions:
- `apply_watermark`: Takes the decrypted plaintext PDF bytes, generates an overlay containing
  the trusted server-side identity (exam, center, user, time), and merges it onto every page.

Why it is required:
To prevent unauthorized distribution of papers, every delivered copy must be individualized.
This allows a leaked paper to be traced back to the exact Center and User who downloaded it.
By doing this in-memory dynamically, we avoid ever saving the plaintext or the watermarked
plaintext to disk, significantly reducing the attack surface.
"""
import io
from datetime import datetime, timezone
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import Color

def create_watermark_overlay(exam_id: int, center_id: int, user_id: int, timestamp: datetime) -> io.BytesIO:
    """
    Creates a single-page PDF containing only the watermark text.
    The text is slanted, semi-transparent, and large so it is highly visible.
    """
    packet = io.BytesIO()
    
    # We use a standard page size; pypdf will merge this over the original pages
    c = canvas.Canvas(packet, pagesize=letter)
    
    # Set a semi-transparent red color
    transparent_red = Color(1, 0, 0, alpha=0.3)
    c.setFillColor(transparent_red)
    c.setFont("Helvetica-Bold", 40)
    
    # Move origin to center, rotate
    c.translate(300, 400)
    c.rotate(45)
    
    # Draw the multiline forensic text
    text = [
        "EXAMINATION PAPER",
        f"EXAM ID: {exam_id}",
        f"CENTER ID: {center_id}",
        f"AUTHORIZED USER ID: {user_id}",
        f"TIMESTAMP: {timestamp.strftime('%Y-%m-%d %H:%M UTC')}"
    ]
    
    y = 0
    for line in text:
        c.drawCentredString(0, y, line)
        y -= 50
        
    c.save()
    packet.seek(0)
    return packet

def apply_watermark(pdf_bytes: bytes, exam_id: int, center_id: int, user_id: int, timestamp: datetime) -> bytes:
    """
    Parses the original PDF bytes, merges the watermark overlay onto every page,
    and returns the new watermarked PDF bytes.
    """
    # Create the watermark overlay
    watermark_packet = create_watermark_overlay(exam_id, center_id, user_id, timestamp)
    watermark_reader = PdfReader(watermark_packet)
    watermark_page = watermark_reader.pages[0]
    
    # Read the original PDF
    pdf_stream = io.BytesIO(pdf_bytes)
    try:
        pdf_reader = PdfReader(pdf_stream)
        pdf_writer = PdfWriter()
        
        # Merge watermark onto every page
        for page in pdf_reader.pages:
            page.merge_page(watermark_page)
            pdf_writer.add_page(page)
            
        output_stream = io.BytesIO()
        pdf_writer.write(output_stream)
        
        watermarked_bytes = output_stream.getvalue()
        return watermarked_bytes
    except Exception as e:
        # If it's not a valid PDF or corrupted, fail closed safely.
        raise ValueError("Failed to parse or watermark PDF") from e
