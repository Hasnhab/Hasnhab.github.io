import os
import re
import json
from mitmproxy import http


pattern = re.compile(
    r'__d\("([^"]+?)_facebookRelayOperation".*?e\.exports\s*=\s*"(\d+)"',
    re.DOTALL
)


desktop = os.path.join(os.path.expanduser("~"), "Desktop")


repo_json_path = os.path.join(desktop, "relay_repository.json")
repo_html_path = os.path.join(desktop, "relay_repository.html")

session_json_path = os.path.join(desktop, "relay_session.json")
session_html_path = os.path.join(desktop, "relay_session.html")

if os.path.exists(repo_json_path):
    with open(repo_json_path, "r", encoding="utf-8") as f:
        repo_entries = json.load(f)
else:
    repo_entries = []

repo_seen = set(f"{m}:{d}" for m, d in repo_entries)


session_entries = []
session_seen = set()

def _init_html_pages():
    _write_repository_html()
    _write_session_html()

def _save_repository():
    with open(repo_json_path, "w", encoding="utf-8") as f:
        json.dump(repo_entries, f, ensure_ascii=False, indent=2)

def _save_session():
    with open(session_json_path, "w", encoding="utf-8") as f:
        json.dump(session_entries, f, ensure_ascii=False, indent=2)

def _write_html_generic(out_path, title, signature="By Hasan Habeeb", entries_list=None):
    entries_list = entries_list or []
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(
            "<!DOCTYPE html>\n"
            "<html lang='en'>\n"
            "<head>\n"
            "  <meta charset='utf-8'>\n"
            f"  <title>{title}</title>\n"
            "  <script>\n"
            "    function downloadFile(filename, text) {\n"
            "      var element = document.createElement('a');\n"
            "      element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));\n"
            "      element.setAttribute('download', filename);\n"
            "      element.style.display = 'none';\n"
            "      document.body.appendChild(element);\n"
            "      element.click();\n"
            "      document.body.removeChild(element);\n"
            "    }\n"
            "    function exportDocIDs() {\n"
            "      var text = '';\n"
            "      var ids = document.querySelectorAll('td.docid');\n"
            "      ids.forEach(td => { text += td.innerText + '\\n'; });\n"
            "      downloadFile('doc_ids.txt', text);\n"
            "    }\n"
            "    function exportModules() {\n"
            "      var text = '';\n"
            "      var mods = document.querySelectorAll('td.module');\n"
            "      mods.forEach(td => { text += td.innerText + '\\n'; });\n"
            "      downloadFile('modules.txt', text);\n"
            "    }\n"
            "    function exportTable() {\n"
            "      var text = '';\n"
            "      var rows = document.querySelectorAll('table tr');\n"
            "      rows.forEach(tr => {\n"
            "        var cols = tr.querySelectorAll('td,th');\n"
            "        var line = [];\n"
            "        cols.forEach(td => { line.push(td.innerText); });\n"
            "        text += line.join('\\t') + '\\n';\n"
            "      });\n"
            "      downloadFile('full_table.txt', text);\n"
            "    }\n"
            "  </script>\n"
            "  <style>\n"
            "    body { font-family: Arial, sans-serif; margin: 18px; }\n"
            "    h3 { margin: 6px 0; }\n"
            "    table { border-collapse: collapse; }\n"
            "    table, th, td { border: 1px solid #999; }\n"
            "    th, td { padding: 6px 10px; }\n"
            "    button { margin-right: 8px; padding: 6px 10px; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            f"  <h3 style='font-family:monospace; color:gray;'>{signature}</h3>\n"
            f"  <h3>{title}</h3>\n"
            "  <button onclick='exportDocIDs()'>Export Doc IDs</button>\n"
            "  <button onclick='exportModules()'>Export Module Names</button>\n"
            "  <button onclick='exportTable()'>Export Full Table</button>\n"
            "  <br><br>\n"
            "  <table border='1' cellspacing='0' cellpadding='5'>\n"
            "    <tr><th>#</th><th>Module Name (Query)</th><th>Doc ID</th></tr>\n"
        )

        for idx, (mod, did) in enumerate(entries_list, start=1):
            f.write(
                f"    <tr><td>{idx}</td>"
                f"<td class='module'>{mod}</td>"
                f"<td class='docid'>{did}</td></tr>\n"
            )

        f.write(
            "  </table>\n"
            "</body>\n"
            "</html>\n"
        )

def _write_repository_html():
    _write_html_generic(repo_html_path, "Relay Repository (All Sessions)")

def _write_session_html():
    _write_html_generic(session_html_path, "Relay Session (Current Run)", entries_list=session_entries)

_init_html_pages()

def response(flow: http.HTTPFlow):
    ctype = flow.response.headers.get("Content-Type", "")
    url = flow.request.pretty_url

    if "javascript" in ctype or url.endswith(".js"):
        text = flow.response.get_text()

        for module, docid in pattern.findall(text):
            key = f"{module}:{docid}"

            if key not in repo_seen:
                repo_seen.add(key)
                repo_entries.append((module, docid))
                print(f"[+] New (repository) #{len(repo_entries)} → {module} : {docid}")
                _save_repository()
                _write_repository_html()

            if key not in session_seen:
                session_seen.add(key)
                session_entries.append((module, docid))
                print(f"[+] New (session) #{len(session_entries)} → {module} : {docid}")
                _save_session()
                _write_session_html()
