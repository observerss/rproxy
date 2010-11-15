#coding:utf-8
#module for quoting chinese characters
import re

def encode_javascript(s):
    try:
        return s.encode('ascii', 'backslashreplace')
    except:
        return s

def encode_xml_entity(data):
    try:
        return data.encode('ascii', 'xmlcharrefreplace')
    except:
        return data

def quote_zh(data, ctype=None):
    if ctype:
        match = re.search(r'charset\s*=\s*(\S+)', ctype)
        charset = match and match.group(1) or None
    else:
        charset = None
    if charset:
        data = data.decode(charset)
    else:
        for charset in ('utf-8', 'gb18030', 'big5'):
            try:
                data = data.decode(charset)
                break
            except:
                pass
    _buffer = []
    last = 0
    in_script = False
    if ctype and 'javascript' in ctype:
        return encode_javascript(data)
    lower_data = data.lower()
    while True:
        if in_script:
            i = lower_data.find('</script>', last)
            if i < 0:
                _buffer.append(encode_javascript(data[last:]))
                break
            _buffer.append(encode_javascript(data[last:i]))
            last = i
            in_script = False
        else:
            i = lower_data.find('<script', last)
            if i < 0:
                _buffer.append(encode_xml_entity(data[last:]))
                break
            _buffer.append(encode_xml_entity(data[last:i]))
            in_script = True
            last = i
    return ''.join(_buffer)


if __name__ == "__main__":
    print quote_zh(u"哈哈，中招了".encode("gb18030"))
