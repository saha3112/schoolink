"""Exports of the already-authorized Marks list; no independent database access."""
import csv
import io
import zipfile
from xml.sax.saxutils import escape
from flask import Response, render_template


def spreadsheet(rows):
    """Small standards-based XLSX writer: inline strings never become formulas."""
    out = io.BytesIO()
    def cell(value, row, col):
        name = ''
        while col:
            col, digit = divmod(col-1, 26)
            name = chr(65+digit) + name
        value = ''.join(ch for ch in str(value) if ord(ch) >= 32 or ch in '\n\r\t')
        return f'<c r="{name}{row}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="8" customWidth="1"/><col min="2" max="2" width="30" customWidth="1"/><col min="3" max="16384" width="22" customWidth="1"/></cols><sheetData>'
    sheet += ''.join('<row r="'+str(i)+'">'+''.join(cell(v,i,j) for j,v in enumerate(row,1))+'</row>' for i,row in enumerate(rows,1))
    sheet += '</sheetData></worksheet>'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Marks" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',sheet)
    return out.getvalue()


def download(fmt, title, filename, subjects, students, grid, excluded):
    columns=[(s,st) for s in subjects for st in s['subtypes']]
    headers=['Roll','Student']+[f"{s['subject_name']} · {st['name']} (Max {st['fullmarks']})" for s,st in columns]
    rows=[[stu['student_rollNumber'],stu['student_name']]+[
        'Not applicable' if (stu['studentId'],s['subjectId']) in excluded else grid.get((stu['studentId'],s['subjectId'],st['subtype_id']), '')
        for s,st in columns] for stu in students]
    if fmt=='pdf':
        from ..blueprints.reports import pdf_response
        # Keep wide class lists readable: repeat Roll/Student for each group of six columns.
        groups=[{'headers':headers[:2]+headers[start:start+6], 'rows':[row[:2]+row[start:start+6] for row in rows]} for start in range(2,len(headers),6)]
        response = pdf_response(render_template('marks_export.html',title=title,groups=groups),filename+'.pdf','A4 landscape')
        response.headers['Cache-Control'] = 'no-store'
        return response
    data=[[title],headers]+rows
    if fmt=='xlsx':
        content=spreadsheet(data)
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        stream=io.StringIO(newline='')
        # CSV applications interpret leading operators as formulas even in quoted cells.
        safe=lambda value: "'"+str(value) if str(value).lstrip().startswith(('=','+','-','@')) else value
        writer=csv.writer(stream,lineterminator='\r\n')
        writer.writerows([[safe(v) for v in row] for row in data])
        content=('\ufeff'+stream.getvalue()).encode('utf-8');mime='text/csv; charset=utf-8'
    return Response(content,mimetype=mime,headers={'Content-Disposition':f'attachment; filename="{filename}.{fmt}"','Cache-Control':'no-store'})
