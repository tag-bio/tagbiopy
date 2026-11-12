"""Unit tests for the Tag.bio report page (tagbiopy.report); no server or kernel needed."""
import json

import nbformat
import plotly.express as px

from tagbiopy import report
from tagbiopy.protocol import FCPacket
from tagbiopy.utils import ipynb_to_html


def make_packet(tmp_path):
    path = tmp_path / 'packet.json'
    path.write_text(json.dumps({
        'request': {'email': 'someone@example.com'},
        'fc': {'name': 'fc-toy', 'url': 'http://localhost:8000/',
               'protocol-url': 'https://demo.tag.bio/node/fc-toy/toy/config',
               'info': {'data_timestamp': 1762900000000}},
        'script': {}, 'passthrough_arguments': {}}))
    return str(path)


def make_notebook(tmp_path):
    fig = px.bar(x=['A', 'B'], y=[1, 2])
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell('# Toy Report'),
        nbformat.v4.new_markdown_cell('## Section One'),
        nbformat.v4.new_code_cell('fig', outputs=[nbformat.v4.new_output(
            'display_data', data={'application/vnd.plotly.v1+json': json.loads(fig.to_json())})]),
        nbformat.v4.new_markdown_cell('### Detail'),
        nbformat.v4.new_markdown_cell('## Section Two'),
    ]
    path = tmp_path / 'toy.ipynb'
    nbformat.write(nb, str(path))
    return str(path)


def test_notebook_report_header_toc_and_plotly(tmp_path):
    out = tmp_path / 'report.html'
    ipynb_to_html(make_notebook(tmp_path), str(out), tag_data=make_packet(tmp_path))
    page = out.read_text()
    assert '<h1 class="title toc-ignore">Toy Report</h1>' in page
    assert 'someone<span>&#64;</span>example.com' in page
    assert 'Data updated on' in page
    assert 'https://demo.tag.bio/node/fc-toy/toy/config' in page
    toc = page[page.index('id="TOC"'):page.index('id="content-wrapper"')]
    assert toc.index('Section One') < toc.index('Detail') < toc.index('Section Two')
    assert '<h2 id="section-one">' in page and '<h3 id="detail">' in page
    assert 'Plotly.newPlot' in page and 'application/vnd.plotly' not in page
    assert 'font/ttf;base64' in page


def test_tag_report_and_banner(tmp_path):
    out = tmp_path / 'page.html'
    report.tag_report('<h2>Results</h2><p>text</p>', 'My App', output_file=str(out),
                      fc_packet=FCPacket(make_packet(tmp_path)))
    report.insert_banner(str(out), '<div>NOTICE</div>')
    page = out.read_text()
    # the notice opens the content: after the header and table of contents, before the first section
    assert page.index('<section class="main-content"><div>NOTICE</div>') > page.index('id="TOC"')
    assert page.index('NOTICE') < page.rindex('Results')


def test_falls_back_to_plain_page_when_report_fails(tmp_path, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        raise RuntimeError('boom')

    class Done:
        def check_returncode(self):
            return None

    def fake_run(cmd):
        calls.append(cmd)
        (tmp_path / 'out.html.html').write_text('<html>plain</html>')
        return Done()

    monkeypatch.setattr(report, 'notebook_report', fail)
    monkeypatch.setattr('subprocess.run', fake_run)
    out = tmp_path / 'out.html'
    ipynb_to_html(make_notebook(tmp_path), str(out))
    assert calls and calls[0][:2] == ['jupyter', 'nbconvert']
    assert out.read_text() == '<html>plain</html>'
