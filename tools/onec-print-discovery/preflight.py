"""Offline source audit; no 1C/API or business data access."""
from pathlib import Path
import re
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent


def audit(root=ROOT):
    source = root / 'src'
    files = list(source.rglob('*'))
    xml = [path for path in files if path.suffix == '.xml']
    bsl = [path for path in files if path.suffix == '.bsl']
    if len(xml) != 3 or len(bsl) != 2:
        raise ValueError('Unexpected source tree')
    trees = [ET.fromstring(path.read_text(encoding='utf-8-sig')) for path in xml]
    if any(tree.attrib.get('version') != '2.14' for tree in trees):
        raise ValueError('Expected reviewed XML 2.14')
    module = next(path for path in bsl if path.name == 'Module.bsl').read_text(encoding='utf-8-sig')
    code = '\n'.join(line.split('//', 1)[0] for line in module.splitlines())
    forbidden = (r'SetStandardOData', r'Execute\s*\(', r'Eval\s*\(', r'New\s+Query\b',
                 r'GetObject\s*\(', r'CreateDocument\s*\(', r'HTTPConnection', r'Privileged',
                 r'ApplyWhitelist', r'Print\s*\(', r'ElseIf', r'StringLength\s*\(')
    if any(re.search(pattern, code, re.I) for pattern in forbidden):
        raise ValueError('Forbidden discovery behavior or incompatible BSL')
    handlers = set(re.findall(r'\b(?:Procedure|Function)\s+(\w+)\s*\(', code, re.I))
    commands = []
    for tree in trees:
        for node in tree.iter():
            local = node.tag.rsplit('}', 1)[-1]
            if local in ('Action', 'Event') and node.text not in handlers:
                raise ValueError('Unwired handler')
            if local == 'Command':
                commands.append(node.attrib['name'])
    if commands != ['Export']:
        raise ValueError('Expected exactly one readonly form command')
    block_code = re.sub(r'"(?:""|[^"])*"', '""', code)
    for opening, ending in [('Procedure', 'EndProcedure'), ('Function', 'EndFunction'),
                            ('Try', 'EndTry'), ('If', 'EndIf'), ('Do', 'EndDo')]:
        if len(re.findall(r'\b' + opening + r'\b', block_code, re.I)) != len(re.findall(r'\b' + ending + r'\b', block_code, re.I)):
            raise ValueError('Unbalanced BSL blocks')
    if 'Metadata.HTTPServices' not in code or 'Metadata.CommonModules' not in code:
        raise ValueError('Missing discovery collections')
    return {'xml_files': len(xml), 'bsl_files': len(bsl), 'form_commands': commands, 'static_audit': 'PASS'}


if __name__ == '__main__':
    import json
    print(json.dumps(audit()))
