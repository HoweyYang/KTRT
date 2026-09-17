# -*- coding: utf-8 -*-
"""联网功能共用的「人话」错误说明。

离线时最烦的就是甩一串 <urlopen error [Errno 11001] getaddrinfo failed>：
用户既看不出是"没网"，也不知道该怎么办。
"""
import socket
import urllib.error

OFFLINE_HINT = '离线状态或网络不可用，该功能需要联网'


def describe(e, doing=''):
    """把异常转成给用户看的一句话；doing 例如 'AI 请求'、'在线联想'。"""
    prefix = (doing + '失败：') if doing else ''
    if isinstance(e, urllib.error.HTTPError):
        # 服务器有响应，属于接口 / 密钥 / 额度问题，不是离线
        return '%s服务返回 HTTP %d' % (prefix, e.code)
    if isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
        reason = getattr(e, 'reason', e)
        if isinstance(reason, socket.timeout) or 'timed out' in str(reason).lower():
            return '%s请求超时。%s' % (prefix, OFFLINE_HINT)
        return '%s%s' % (prefix, OFFLINE_HINT)
    return '%s%s' % (prefix, e)
