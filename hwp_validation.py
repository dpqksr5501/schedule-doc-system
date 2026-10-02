"""Check the HWP 5 container, not just the generic OLE magic or extension.

This is structural validation; rendering still requires the destination Hancom.
Reference: https://tech.hancom.com/python-hwp-parsing-1/
"""
from pathlib import Path
import olefile


def validate_hwp(path):
    path = Path(path)
    try:
        with olefile.OleFileIO(str(path), raise_defects=olefile.DEFECT_INCORRECT) as document:
            if document.get_size('FileHeader') != 256:
                raise ValueError('HWP 파일 머리글의 크기가 올바르지 않습니다.')
            header = document.openstream('FileHeader').read(256)
            if header[:32] != b'HWP Document File'.ljust(32, b'\x00') or header[35] != 5:
                raise ValueError('한글 HWP 5 형식의 문서가 아닙니다.')
            flags = int.from_bytes(header[36:40], 'little')
            if flags & 6:
                raise ValueError('암호 또는 배포용 문서가 아닌 편집 가능한 HWP가 필요합니다.')
            for stream in ('DocInfo', 'BodyText/Section0'):
                if document.get_type(stream) != olefile.STGTY_STREAM or document.get_size(stream) == 0:
                    raise ValueError('HWP 문서 정보 또는 본문이 없습니다.')
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise ValueError('HWP 저장 결과를 확인하지 못했습니다. ' + str(error)) from error
    return path
