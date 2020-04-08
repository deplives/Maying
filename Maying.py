#!/usr/bin/python3
# -*- coding: utf-8 -*-

import base64
import json
import sys
import time

import oss2
import requests
from bs4 import BeautifulSoup


def timestamp(dt):
    timeArray = time.strptime(dt, "%Y-%m-%d %H:%M:%S")
    return time.mktime(timeArray)


def base64encode(string):
    bytestr = string.encode(encoding="utf-8")
    encode_str = base64.urlsafe_b64encode(bytestr)
    return str(encode_str, encoding="utf-8")


def base64decode(b64string):
    padding = len(b64string) % 4
    b64string += "=" * padding
    try:
        return base64.urlsafe_b64decode(b64string).decode('utf-8')
    except Exception:
        raise RuntimeError


class Config(dict):
    def __init__(self, conf):
        self.fileObj = open(conf, 'r', encoding='utf8')
        super().__init__(json.loads(self.fileObj.read()))


class OSS(object):
    def __init__(self, configObj):
        self.conf = configObj
        self.ACCESS_KEY_ID = configObj['oss']['ACCESS_KEY_ID']
        self.ACCESS_KEY_SECRET = configObj['oss']['ACCESS_KEY_SECRET']
        self.BUCKET = configObj['oss']['BUCKET']
        self.ENDPOINT = configObj['oss']['ENDPOINT']
        self.FILENAME = configObj['oss']['FILENAME']

        self.auth = oss2.Auth(self.ACCESS_KEY_ID, self.ACCESS_KEY_SECRET)

        self.bucket = oss2.Bucket(self.auth, self.ENDPOINT, self.BUCKET)

        self.suburl = f"https://{self.BUCKET}.{self.ENDPOINT}/{self.FILENAME}"

    def push(self, nodesinfo, extrainfo):
        headers = {
            "x-oss-persistent-headers": f"Subscription-Userinfo:{extrainfo}"
        }
        self.bucket.put_object(self.FILENAME, nodesinfo, headers=headers)


class Node(object):
    def __init__(self, link):
        self.__link__ = link
        self.server = None  # 服务器
        self.port = None  # 端口
        self.protocol = None  # 协议
        self.method = None  # 加密方法
        self.obfs = None  # 混淆
        self.password = None  # 密码
        self.protoparam = None  # 协议参数
        self.obfsparam = None  # 混淆参数
        self.remarks = None  # 备注
        self.group = None  # 分组

        self.id = None  # Maying 节点ID
        self.magnification = None  # Maying 倍率
        self.burden = None  # Maying 负载

        self.init()

    def init(self):
        decode_str = base64decode(self.__link__[6:])  # 解码ssr链接
        parts_list = decode_str.split(':')  # [server:port:protocol:method:obfs:参数]
        assert (len(parts_list) == 6), "ssr链接不正确"

        self.server = parts_list[0]
        self.port = parts_list[1]
        self.protocol = parts_list[2]
        self.method = parts_list[3]
        self.obfs = parts_list[4]

        password_b64, parameters = parts_list[5].split("/?")
        self.password = base64decode(password_b64)
        parameters_list = parameters.split("&")
        parameters_dict = {}
        for item in parameters_list:
            k, v = item.split('=')
            parameters_dict[k] = base64decode(v)

        self.obfsparam = parameters_dict['obfsparam']
        self.protoparam = parameters_dict['protoparam']
        self.remarks = parameters_dict['remarks']
        self.group = parameters_dict['group']

        if self.group.upper() == 'MAYING':
            remarks_detail = self.remarks.split('-')
            remarks_detail.append('')

            self.id = remarks_detail[0]
            self.magnification = remarks_detail[1]

    @property
    def link(self):
        lstr = ""
        lstr += f"{self.server}:"
        lstr += f"{self.port}:"
        lstr += f"{self.protocol}:"
        lstr += f"{self.method}:"
        lstr += f"{self.obfs}:"
        lstr += f"{base64encode(self.password)}/?"
        lstr += f"obfsparam={base64encode(self.obfsparam)}&"
        lstr += f"protoparam={base64encode(self.protoparam)}&"
        lstr += f"remarks={base64encode(self.remarks)}&"
        lstr += f"group={base64encode(self.group)}"
        return 'ssr://' + base64encode(lstr)

    def __str__(self):
        return self.id


class Maying(object):
    def __init__(self, configObj):
        self.conf = configObj
        self.oss = OSS(configObj)
        self.session = requests.Session()
        self.session.proxies = configObj['proxy']
        self.session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36"
        }

        self.nodes = dict()

        self.signin()

    def signin(self):
        url = self.conf['url']['signin']
        data = {'email': self.conf['login']['email'], 'passwd': self.conf['login']['passwd']}

        resp = self.session.post(url, data=data)
        return True if resp.status_code == 200 else False

    def subscribe(self, burden=True):
        suburl = self.conf['url']['subscribe']
        nodes = {}
        nodes_base64 = self.session.get(suburl, timeout=5).text
        nodes_list = base64decode(nodes_base64).strip().split("\n")

        for n in nodes_list[2:]:  # 前两个是订阅信息，无节点
            node = Node(n)
            if node.id in config['custom']:
                nodes[node.id] = node

        flowinfo = Node(nodes_list[0]).remarks.split("：")[-1].split(" ")
        remaining = float(flowinfo[-1][:-2])
        total = remaining / (float(flowinfo[0][:-1]) / 100)
        download = total - float(flowinfo[-1][:-2])
        expire = Node(nodes_list[1]).remarks.split("：")[-1]

        nodeurl = self.conf['url']['node']
        resp = self.session.get(nodeurl)
        soup = BeautifulSoup(resp.text, 'lxml')
        divs = soup.findAll('div', attrs={'class': 'text-overflow'})
        nodesdict = {}
        for div in divs:
            div.i.decompose()
            text = list(map(lambda x: x.strip(), div.get_text().strip().split('|')))
            nodesdict[text[0].split('-')[0]] = text[1][2:].strip()

        for k, v in nodes.items():
            v.burden = nodesdict[k]
            if burden:
                v.remarks += f" ({v.burden})"
            self.nodes[k] = v

        ssrlist = [ssr.link for ssr in self.nodes.values()]
        newsub = base64encode("\n".join(ssrlist))
        userinfo = f"upload=0; download={download * 1024 * 1024 * 1024}; total={total * 1024 * 1024 * 1024}; expire={timestamp(expire)}"
        self.oss.push(newsub, base64encode(userinfo))


if __name__ == '__main__':
    config = Config('maying.json')
    maying = Maying(config)
    sys.argv.append('')
    isburden = True if sys.argv[1] == 'burden' else False
    maying.subscribe(isburden)
