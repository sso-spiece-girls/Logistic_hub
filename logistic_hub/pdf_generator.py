import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

DARK = HexColor("#000000")
GRAY_LIGHT = HexColor("#f5f5f5")
GRAY_BORDER = HexColor("#cccccc")
GRAY_TEXT = HexColor("#666666")
BLUE_LIGHT = HexColor("#e8f0fe")

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "logo.png")

PAGE_W = 190*mm
COL_HALF = 95*mm


def _styles():
    s = {}
    s['title'] = ParagraphStyle('t', fontSize=11, leading=13, fontName='Helvetica-Bold', alignment=TA_CENTER)
    s['sub'] = ParagraphStyle('sub', fontSize=7.5, leading=9, fontName='Helvetica', textColor=GRAY_TEXT)
    s['label'] = ParagraphStyle('l', fontSize=7, leading=9, fontName='Helvetica-Bold')
    s['val'] = ParagraphStyle('v', fontSize=8.5, leading=11, fontName='Helvetica')
    s['val_bold'] = ParagraphStyle('vb', fontSize=8.5, leading=11, fontName='Helvetica-Bold')
    s['th'] = ParagraphStyle('th', fontSize=7, leading=9, fontName='Helvetica-Bold', alignment=TA_CENTER)
    s['td'] = ParagraphStyle('td', fontSize=7.5, leading=9, fontName='Helvetica', alignment=TA_CENTER)
    s['td_l'] = ParagraphStyle('tdl', fontSize=7.5, leading=9, fontName='Helvetica', alignment=TA_LEFT)
    s['footer'] = ParagraphStyle('f', fontSize=6.5, leading=8, fontName='Helvetica', textColor=GRAY_TEXT, alignment=TA_CENTER)
    return s


def _section_box(title, content_items, style, col_width=COL_HALF):
    """Create a labeled section box with key-value pairs."""
    data = [[Paragraph(f'<b>{title}</b>', style['label'])]]
    for k, v in content_items:
        data.append([
            Paragraph(f'{k}:', style['label']),
            Paragraph(str(v) if v else '', style['val']),
        ])
    t = Table(data, colWidths=[col_width*0.3, col_width*0.7])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GRAY_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('SPAN', (0, 0), (-1, 0)),
    ]))
    return t


def genera_ddt_pdf(ddt_data, righe):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.2*cm, bottomMargin=1.8*cm,
    )
    S = _styles()
    elems = []

    # ===== INTESTAZIONE =====
    addr_lines = [
        'Logistic Solution S.r.l.',
        'Via Napoli 22, 57014 Collesalvetti (LI)',
        'Tel: +39 0586 123456 | P.IVA: IT01234560456',
    ]
    header_text = f'''
    <b>{addr_lines[0]}</b><br/>
    {addr_lines[1]}<br/>
    {addr_lines[2]}
    '''
    header = Paragraph(header_text, ParagraphStyle('h', fontSize=8.5, leading=11, fontName='Helvetica', alignment=TA_CENTER))
    elems.append(header)
    elems.append(Spacer(1, 3))
    elems.append(Table([['']], colWidths=[PAGE_W], style=TableStyle([('LINEBELOW', (0,0), (-1,0), 0.5, GRAY_BORDER)])))
    elems.append(Spacer(1, 6))

    # ===== TITOLO =====
    elems.append(Paragraph('DOCUMENTO DI TRASPORTO (D.P.R. 472 del 14/08/96)', S['title']))
    elems.append(Spacer(1, 6))

    # ===== CLIENTE / DESTINAZIONE =====
    cliente_block = [
        ['<b>Merce proveniente da:</b>', ''],
        ['Logistic Solution S.r.l.', ''],
        ['Via Napoli 22', ''],
        ['Collesalvetti (LI)', ''],
    ]
    dest_block = [
        ['<b>Cliente</b>', ''],
        [ddt_data.get('cliente', ''), ''],
    ]
    if ddt_data.get('destinatario') and ddt_data['destinatario'] != ddt_data.get('cliente'):
        dest_block.append(['<b>Destinazione Merce</b>', ''])
        dest_block.append([ddt_data['destinatario'], ''])

    max_rows = max(len(cliente_block), len(dest_block))
    while len(cliente_block) < max_rows:
        cliente_block.append(['', ''])
    while len(dest_block) < max_rows:
        dest_block.append(['', ''])

    left_data = [[Paragraph(c[0], S['val_bold'] if '<b>' in c[0] else S['val']),
                  Paragraph(c[1], S['val'])] for c in cliente_block]
    right_data = [[Paragraph(c[0], S['val_bold'] if '<b>' in c[0] else S['val']),
                   Paragraph(c[1], S['val'])] for c in dest_block]

    addr_table = Table(
        [left_data[i] + right_data[i] for i in range(max_rows)],
        colWidths=[COL_HALF*0.3, COL_HALF*0.2, COL_HALF*0.3, COL_HALF*0.2]
    )
    addr_table.setStyle(TableStyle([
        ('BOX', (0, 0), (1, max_rows-1), 0.5, GRAY_BORDER),
        ('BOX', (2, 0), (3, max_rows-1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (1, max_rows-1), 0.3, GRAY_BORDER),
        ('INNERGRID', (2, 0), (3, max_rows-1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elems.append(addr_table)
    elems.append(Spacer(1, 6))

    # ===== RIGA DDT =====
    ddt_info = [
        Paragraph(f'<b>D.D.T. n° {ddt_data["numero_ddt"]}</b>', S['val_bold']),
        Paragraph(f'<b>del {ddt_data["data"]}</b>', S['val_bold']),
        Paragraph('Pagina:', S['label']),
        Paragraph('<b>1</b>', S['val']),
    ]
    ddt_row = Table([ddt_info], colWidths=[PAGE_W*0.3, PAGE_W*0.3, PAGE_W*0.1, PAGE_W*0.3])
    ddt_row.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elems.append(ddt_row)
    elems.append(Spacer(1, 3))

    # ===== PARTITA IVA / CAUSALE / PORTO =====
    extra_data = [
        [Paragraph('Partita Iva', S['label']), Paragraph('IT01234560456', S['val']),
         Paragraph('Causale Trasp.:', S['label']), Paragraph(ddt_data.get('causale_trasporto', 'Vendita'), S['val'])],
        [Paragraph('Codice Fiscale', S['label']), Paragraph('', S['val']),
         Paragraph('Porto:', S['label']), Paragraph('', S['val'])],
    ]
    if ddt_data.get('vettore'):
        extra_data.append([
            Paragraph('Vettore:', S['label']), Paragraph(ddt_data['vettore'], S['val']),
            Paragraph('', S['label']), Paragraph('', S['val']),
        ])
    extra_table = Table(extra_data, colWidths=[PAGE_W*0.12, PAGE_W*0.38, PAGE_W*0.12, PAGE_W*0.38])
    extra_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elems.append(extra_table)
    elems.append(Spacer(1, 6))

    # ===== TABELLA MERCI =====
    totali = {
        'colli': sum((r.get('quantita_colli', 0) or 0) for r in righe),
        'pallet': sum((r.get('quantita_pallet', 0) or 0) for r in righe),
        'peso': sum((r.get('peso_kg', 0) or 0) for r in righe),
    }

    headers = ['<b>Cod. Articolo</b>', '<b>Descrizione</b>', '<b>UMP</b>', '<b>Quantità</b>']
    rows = [[Paragraph(h, S['th']) for h in headers]]

    for r in righe:
        codice = r.get('articolo_codice', '')
        desc = r.get('descrizione', '')
        colli = r.get('quantita_colli', 0) or 0
        ump = 'Colli'
        qty = str(colli)
        rows.append([
            Paragraph(codice, S['td']),
            Paragraph(desc, S['td_l']),
            Paragraph(ump, S['td']),
            Paragraph(qty, S['td']),
        ])

    if totali['colli'] > 0:
        rows.append([
            Paragraph('<b>TOTALE</b>', ParagraphStyle('tot_l', fontSize=8, leading=10, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
            Paragraph('', S['td']),
            Paragraph('', S['td']),
            Paragraph(f'<b>{totali["colli"]}</b>', ParagraphStyle('tot_v', fontSize=8, leading=10, fontName='Helvetica-Bold', alignment=TA_CENTER)),
        ])

    col_w = [PAGE_W*0.22, PAGE_W*0.48, PAGE_W*0.12, PAGE_W*0.18]
    merci_table = Table(rows, colWidths=col_w, repeatRows=1)
    merci_style = [
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]
    if totali['colli'] > 0:
        merci_style.append(('BACKGROUND', (0, -1), (-1, -1), GRAY_LIGHT))
        merci_style.append(('LINEABOVE', (0, -1), (-1, -1), 1, DARK))
    merci_table.setStyle(TableStyle(merci_style))
    elems.append(merci_table)
    elems.append(Spacer(1, 8))

    # ===== PIEDE: Totali / Vettore / Date =====
    footer_rows = []

    # Riga 1: Aspetto esteriore, Totale colli, Data ritiro
    footer_rows.append([
        Paragraph('Aspetto esteriore:', S['label']),
        Paragraph(f'<b>Totale colli: {totali["colli"]}</b>', S['val_bold']),
        Paragraph('', S['val']),
    ])

    if ddt_data.get('provenienza'):
        footer_rows.append([
            Paragraph('Provenienza:', S['label']),
            Paragraph(ddt_data['provenienza'], S['val']),
            Paragraph('', S['val']),
        ])

    # Riga 2: Data Trasp., Vettore
    footer_rows.append([
        Paragraph(f'Data Trasp.: {ddt_data["data"]}', S['val']),
        Paragraph(f'Vettore: {ddt_data.get("vettore", "")}', S['val']),
        Paragraph(f'Peso: {totali["peso"]:.2f} kg' if totali['peso'] else '', S['val']),
    ])

    footer_table = Table(footer_rows, colWidths=[PAGE_W*0.35, PAGE_W*0.35, PAGE_W*0.30])
    footer_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elems.append(footer_table)
    elems.append(Spacer(1, 4))

    # ===== NOTE =====
    note_data = [
        [Paragraph('<b>Annotazioni e variazioni:</b>', S['label']), Paragraph('<b>Note:</b>', S['label'])],
        [Paragraph('', S['val']), Paragraph('', S['val'])],
    ]
    note_table = Table(note_data, colWidths=[PAGE_W*0.5, PAGE_W*0.5])
    note_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elems.append(note_table)
    elems.append(Spacer(1, 10))

    # ===== FIRME =====
    firme_data = [
        [Paragraph('', S['val']), Paragraph('', S['val']), Paragraph('', S['val'])],
        [Paragraph('Firma del conducente', S['label']),
         Paragraph('Firma del vettore', S['label']),
         Paragraph('Firma per accettazione', S['label'])],
    ]
    firme_table = Table(firme_data, colWidths=[PAGE_W*0.33, PAGE_W*0.33, PAGE_W*0.34])
    firme_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 0.5, GRAY_TEXT),
        ('LINEABOVE', (1, 0), (1, 0), 0.5, GRAY_TEXT),
        ('LINEABOVE', (2, 0), (2, 0), 0.5, GRAY_TEXT),
        ('TOPPADDING', (0, 0), (-1, 0), 24),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elems.append(firme_table)

    # ===== FOOTER =====
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GRAY_BORDER)
        canvas.line(1.8*cm, 1.5*cm, A4[0]-1.8*cm, 1.5*cm)
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(GRAY_TEXT)
        canvas.drawString(1.8*cm, 1.2*cm,
            f'Documento generato automaticamente da Logistic Solution S.r.l. | {datetime.now().strftime("%d/%m/%Y %H:%M")}')
        canvas.restoreState()

    doc.build(elems, onFirstPage=footer, onLaterPages=footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes