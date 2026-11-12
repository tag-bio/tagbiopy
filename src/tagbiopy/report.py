"""
Tag.bio report page for Python plugins: the same header, table of contents, fonts and styling as the R SDK's
``tagbio::tag_report`` (R Markdown apps), as one self-contained HTML file.

``ipynb_to_html`` (papermill notebook apps) uses it by default; ``.py`` plugins that build their own HTML call
``tag_report`` directly.
"""
import base64
import json
import html as html_lib
import os
import re
from datetime import date

RESOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'report')
FONTS = ['Barlow-Regular', 'Barlow-Bold', 'Barlow-Italic', 'Barlow-BoldItalic']
LOGO_LINK = ('https://tag.bio?utm_source=tagbio_analysis_platform&utm_medium=python_report'
             '&utm_content=report_title_logo')

# Rules for notebook output that the R stylesheet has no counterpart for.
EXTRA_CSS = """
.main-content img { max-width: 100%; height: auto; }
.main-content .table-wrapper, .main-content .dataframe-wrapper { overflow-x: auto; }
.main-content table.dataframe { border-collapse: collapse; margin: 1em 0; font-size: 0.9em; }
.main-content table.dataframe th, .main-content table.dataframe td { padding: 4px 8px; border-bottom: 1px solid #e1e4e8; }
.main-content pre { white-space: pre-wrap; }
.main-content .jp-OutputPrompt, .main-content .jp-InputPrompt, .main-content .prompt { display: none; }
.main-content .anchor-link { display: none; }
"""

# The packet of the plugin running in this process, so reports can fill the header without being passed it.
_current_packet = None


def set_current_packet(fc_packet):
    global _current_packet
    _current_packet = fc_packet


def _data_uri(path, mime):
    with open(path, 'rb') as fh:
        return f'data:{mime};base64,' + base64.b64encode(fh.read()).decode('ascii')


def _stylesheet():
    with open(os.path.join(RESOURCES, 'default-color.css'), encoding='utf-8') as fh:
        css = fh.read()
    for font in FONTS:
        css = css.replace(f'url("fonts/{font}.ttf") format("ttf")',
                          f'url("{_data_uri(os.path.join(RESOURCES, font + ".ttf"), "font/ttf")}") format("truetype")')
    return css + EXTRA_CSS


def header_fields(fc_packet=None):
    """
    The report header's user, app link and data date, from a plugin's FCPacket (or the packet of the plugin
    running in this process). Missing values are empty strings.
    """
    packet = fc_packet if fc_packet is not None else _current_packet
    fields = {'email': '', 'analysis_url': '', 'data_updated': ''}
    if packet is None:
        return fields
    raw = getattr(packet, '_packet', None) or {}
    fields['email'] = (raw.get('request') or {}).get('email') or ''
    fields['analysis_url'] = (raw.get('fc') or {}).get('protocol-url') or ''
    ts = (getattr(packet, 'info', None) or {}).get('data_timestamp')
    if ts:
        from datetime import datetime
        fields['data_updated'] = datetime.fromtimestamp(int(ts) // 1000).strftime('%F %X')
    return fields


def _slug(text, used):
    base = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'
    slug, n = base, 1
    while slug in used:
        n += 1
        slug = f'{base}-{n}'
    used.add(slug)
    return slug


def _number_sections_and_toc(body):
    """Give every h2/h3 a stable id and build the nested table of contents the R reports show."""
    used = set()
    entries = []

    def fix(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        text = html_lib.unescape(re.sub(r'<[^>]+>', '', inner)).replace('¶', '').strip()
        if not text:
            return m.group(0)
        slug = _slug(text, used)
        attrs = re.sub(r'\s*id="[^"]*"', '', attrs)
        entries.append((int(level), slug, text))
        return f'<h{level}{attrs} id="{slug}">{inner}</h{level}>'

    body = re.sub(r'<h([23])([^>]*)>(.*?)</h\1>', fix, body, flags=re.S)
    if not entries:
        return body, ''
    # h3 entries nest under the h2 before them (top level when there is none)
    tree = []
    for level, slug, text in entries:
        link = f'<a href="#{slug}">{html_lib.escape(text)}</a>'
        if level == 3 and tree:
            tree[-1][1].append(link)
        else:
            tree.append((link, []))
    items = ''.join(f'<li>{link}' + (f'<ul>{"".join(f"<li>{c}</li>" for c in kids)}</ul>' if kids else '') + '</li>'
                    for link, kids in tree)
    return body, ('<div id="TOC" class="toc"><div class="inner">'
                  f'<h2 id="toc-title" class="toc-title">Table of Contents</h2><ul>{items}</ul></div></div>')


def tag_report(body_html, title, output_file=None, fc_packet=None, toc=True, head_html=''):
    """
    Wrap report content in the Tag.bio report page (header, table of contents, fonts, footer).

    :param body_html: str, the report content (HTML fragment; h2/h3 headings become the table of contents)
    :param title: str, the report title shown in the header
    :param output_file: str, optional; when given, the page is written there (e.g. ``tag_result.path``)
    :param fc_packet: FCPacket, optional; header user, app link and data date (default: the running plugin's)
    :param toc: bool, include the table of contents
    :param head_html: str, extra markup for <head> (e.g. scripts the content needs)
    :return: str, the full HTML page
    """
    fields = header_fields(fc_packet)
    email = html_lib.escape(fields['email'] or os.environ.get('USER', '')).replace('@', '<span>&#64;</span>')
    url = fields['analysis_url'].replace('https://', '')
    body, toc_html = _number_sections_and_toc(body_html)
    info = f'Generated by {email} on {date.today().isoformat()}'
    if fields['data_updated']:
        info += f'<br>Data updated on {html_lib.escape(fields["data_updated"])}'
    url_html = (f'<div class="analysis-url">Analysis URL: <a href="https://{html_lib.escape(url)}" target="_blank">'
                f'https://{html_lib.escape(url)}</a></div>') if url else ''
    logo = _data_uri(os.path.join(RESOURCES, 'tagbio-logo-full-hoz-white.png'), 'image/png')
    page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html_lib.escape(title)}</title>
<style type="text/css">
{_stylesheet()}
</style>
{head_html}
</head>
<body>
<section class="page-header">
  <div class="inner">
    <div class="content">
      <h1 class="title toc-ignore">{html_lib.escape(title)}</h1>
      <div class="report-generated-info">{info}</div>
      {url_html}
    </div>
    <div class="logo"><a href="{LOGO_LINK}" target="_blank"><img src="{logo}" alt="Tag.bio Logo" /></a></div>
  </div>
</section>
{toc_html if toc else ''}
<div id="content-wrapper">
  <div class="inner clearfix">
    <section class="main-content">
{body}
    </section>
  </div>
</div>
</body>
</html>
"""
    if output_file is not None:
        with open(output_file, 'w', encoding='utf-8') as fh:
            fh.write(page)
    return page


def _plotly_outputs_to_html(nb):
    """Plotly figures in a notebook carry only plotly's JSON; draw them as HTML, embedding plotly.js once."""
    first = True
    for cell in nb.cells:
        for output in cell.get('outputs', []):
            data = output.get('data', {})
            spec = data.get('application/vnd.plotly.v1+json')
            if spec is None:
                continue
            import plotly.io as pio
            fig = pio.from_json(spec if isinstance(spec, str) else json.dumps(spec))
            data['text/html'] = pio.to_html(fig, full_html=False, include_plotlyjs=first)
            del data['application/vnd.plotly.v1+json']
            first = False


def _shift_headings(body):
    """Make the notebook's top heading level h2 (the R reports' section level), keeping relative levels."""
    levels = [int(x) for x in re.findall(r'<h([1-6])[\s>]', body)]
    if not levels or min(levels) == 2:
        return body
    shift = min(levels) - 2
    return re.sub(r'<(/?)h([1-6])([\s>])', lambda m: f'<{m.group(1)}h{min(6, max(2, int(m.group(2)) - shift))}{m.group(3)}', body)


def notebook_report(notebook_file, output_file, title=None, fc_packet=None, toc=True):
    """
    Convert an executed notebook (code cells hidden) into a Tag.bio report page.

    The title is ``title`` or else the notebook's first heading (which then moves into the header).
    """
    from nbconvert import HTMLExporter

    import nbformat

    nb = nbformat.read(notebook_file, as_version=4)
    _plotly_outputs_to_html(nb)
    exporter = HTMLExporter(template_name='basic')
    exporter.exclude_input = True
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True
    body, _ = exporter.from_notebook_node(nb)
    if title is None:
        m = re.search(r'<h([1-6])[^>]*>(.*?)</h\1>', body, flags=re.S)
        if m:
            title = html_lib.unescape(re.sub(r'<[^>]+>', '', m.group(2))).replace('\u00b6', '').strip()
            body = body[:m.start()] + body[m.end():]
        else:
            title = os.path.splitext(os.path.basename(notebook_file))[0].replace('_', ' ').title()
    body = _shift_headings(body)
    return tag_report(body, title, output_file=output_file, fc_packet=fc_packet, toc=toc)


def insert_banner(html_path, banner_html):
    """Insert a notice (warning, data note) at the top of a report's content; works on Tag.bio and plain pages."""
    with open(html_path, encoding='utf-8') as fh:
        page = fh.read()
    for anchor in ('<section class="main-content">', '<body'):
        i = page.find(anchor)
        if i != -1:
            j = page.find('>', i)
            page = page[:j + 1] + banner_html + page[j + 1:]
            break
    else:
        page = banner_html + page
    with open(html_path, 'w', encoding='utf-8') as fh:
        fh.write(page)
