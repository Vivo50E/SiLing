"""Small macOS Keychain adapter; values never pass through argv or plaintext files."""
import ctypes as C
import json
import re
import sys


class KeychainError(ValueError):
    pass


class Keychain:
    service = 'SiLing.JiraMCP.OAuth.v1'

    def __init__(self, account):
        if not re.fullmatch(r'[a-f0-9]{32}', account):
            raise KeychainError('invalid_keychain_account')
        if sys.platform != 'darwin':
            raise KeychainError('keychain_unavailable')
        self.account = account
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.sec = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        signatures = {
            'CFStringCreateWithCString': (C.c_void_p, [C.c_void_p,C.c_char_p,C.c_uint32]),
            'CFDataCreate': (C.c_void_p,[C.c_void_p,C.c_void_p,C.c_long]),
            'CFDataGetLength': (C.c_long,[C.c_void_p]),
            'CFDataGetBytePtr': (C.c_void_p,[C.c_void_p]),
            'CFDictionaryCreateMutable': (C.c_void_p,[C.c_void_p,C.c_long,C.c_void_p,C.c_void_p]),
            'CFDictionarySetValue': (None,[C.c_void_p,C.c_void_p,C.c_void_p]),
            'CFRelease': (None,[C.c_void_p]),
        }
        for name,(result,args) in signatures.items():
            fn=getattr(self.cf,name);fn.restype=result;fn.argtypes=args
        for name,args in {'SecItemCopyMatching':[C.c_void_p,C.POINTER(C.c_void_p)],
                          'SecItemAdd':[C.c_void_p,C.c_void_p],
                          'SecItemUpdate':[C.c_void_p,C.c_void_p], 'SecItemDelete':[C.c_void_p]}.items():
            fn=getattr(self.sec,name);fn.restype=C.c_int32;fn.argtypes=args

    def constant(self, name):
        lib = self.cf if name.startswith('kCF') else self.sec
        return C.c_void_p.in_dll(lib,name).value

    def dictionary(self, values):
        keycb=C.addressof(C.c_byte.in_dll(self.cf,'kCFTypeDictionaryKeyCallBacks'))
        valcb=C.addressof(C.c_byte.in_dll(self.cf,'kCFTypeDictionaryValueCallBacks'))
        result=self.cf.CFDictionaryCreateMutable(None,0,keycb,valcb)
        owned=[]
        for key,value in values.items():
            if isinstance(value,str):
                obj=self.cf.CFStringCreateWithCString(None,value.encode(),0x08000100);owned.append(obj)
            elif isinstance(value,bytes):
                buffer=C.create_string_buffer(value)
                obj=self.cf.CFDataCreate(None,buffer,len(value));owned.append(obj)
            else:obj=value
            self.cf.CFDictionarySetValue(result,self.constant(key),obj)
        for obj in owned:self.cf.CFRelease(obj)
        return result

    def query(self, extra=None):
        return self.dictionary({'kSecClass':self.constant('kSecClassGenericPassword'),
                                'kSecAttrService':self.service,'kSecAttrAccount':self.account,
                                'kSecUseAuthenticationUI':self.constant('kSecUseAuthenticationUIFail'), **(extra or {})})

    def get(self):
        query=self.query({'kSecReturnData':self.constant('kCFBooleanTrue')})
        result=C.c_void_p()
        try:code=self.sec.SecItemCopyMatching(query,C.byref(result))
        finally:self.cf.CFRelease(query)
        if code == -25300:return None
        if code != 0:raise KeychainError('keychain_unavailable')
        try:
            size=self.cf.CFDataGetLength(result)
            if size>65536:raise KeychainError('keychain_unavailable')
            data=json.loads(C.string_at(self.cf.CFDataGetBytePtr(result),size))
            if not isinstance(data,dict):raise KeychainError('keychain_unavailable')
            return data
        finally:self.cf.CFRelease(result)

    def set(self, value):
        raw=json.dumps(value).encode()
        if len(raw)>65536:raise KeychainError('keychain_unavailable')
        query=self.query();attrs=self.dictionary({'kSecValueData':raw})
        try:code=self.sec.SecItemUpdate(query,attrs)
        finally:self.cf.CFRelease(query);self.cf.CFRelease(attrs)
        if code == -25300:
            query=self.query({'kSecValueData':raw,'kSecAttrAccessible':self.constant('kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly')})
            try:code=self.sec.SecItemAdd(query,None)
            finally:self.cf.CFRelease(query)
        if code != 0:raise KeychainError('keychain_unavailable')

    def delete(self):
        query=self.query()
        try:code=self.sec.SecItemDelete(query)
        finally:self.cf.CFRelease(query)
        if code not in (0,-25300):raise KeychainError('keychain_unavailable')
