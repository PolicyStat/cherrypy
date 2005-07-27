"""
Copyright (c) 2005, CherryPy Team (team@cherrypy.org)
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, 
are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice, 
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice, 
      this list of conditions and the following disclaimer in the documentation 
      and/or other materials provided with the distribution.
    * Neither the name of the CherryPy Team nor the names of its contributors 
      may be used to endorse or promote products derived from this software 
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND 
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE 
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL 
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER 
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, 
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE 
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

"""Basic tests for the CherryPy core: request handling."""

import cherrypy
import types

class Root:
    def index(self):
        return "hello"
    index.exposed = True

cherrypy.root = Root()


class TestType(type):
    def __init__(cls, name, bases, dct):
        type.__init__(name, bases, dct)
        for value in dct.itervalues():
            if isinstance(value, types.FunctionType):
                value.exposed = True
        setattr(cherrypy.root, name.lower(), cls())
class Test(object):
    __metaclass__ = TestType


class Params(Test):
    
    def index(self, thing):
        return thing


class Status(Test):
    
    def index(self):
        return "normal"
    
    def blank(self):
        cherrypy.response.status = ""
    
    # According to RFC 2616, new status codes are OK as long as they
    # are between 100 and 599.
    
    # Here is an illegal code...
    def illegal(self):
        cherrypy.response.status = 781
        return "oops"
    
    # ...and here is an unknown but legal code.
    def unknown(self):
        cherrypy.response.status = "431 My custom error"
        return "funky"
    
    # Non-numeric code
    def bad(self):
        cherrypy.response.status = "error"
        return "hello"


class Redirect(Test):
    
    def index(self):
        return "child"
    
    def by_code(self, code):
        raise cherrypy.HTTPRedirect("somewhere else", code)
    
    def nomodify(self):
        raise cherrypy.HTTPRedirect("", 304)
    
    def proxy(self):
        raise cherrypy.HTTPRedirect("proxy", 305)
    
    def internal(self):
        raise cherrypy.InternalRedirect("/")
    
    def internal2(self, user_id):
        if user_id == "parrot":
            # Trade it for a slug when redirecting
            raise cherrypy.InternalRedirect('/image/getImagesByUser',
                                           "user_id=slug")
        elif user_id == "terrier":
            # Trade it for a fish when redirecting
            raise cherrypy.InternalRedirect('/image/getImagesByUser',
                                           {"user_id": "fish"})
        else:
            raise cherrypy.InternalRedirect('/image/getImagesByUser')


class Image(Test):
    
    def getImagesByUser(self, user_id):
        return "0 images for %s" % user_id


class Flatten(Test):
    
    def as_string(self):
        return "content"
    
    def as_list(self):
        return ["con", "tent"]
    
    def as_yield(self):
        yield "content"
    
    def as_dblyield(self):
        yield self.as_yield()
    
    def as_refyield(self):
        for chunk in self.as_yield():
            yield chunk


class Error(Test):
    
    def page_method(self):
        raise ValueError
    
    def page_yield(self):
        yield "hello"
        raise ValueError
    
    def page_http_1_1(self):
        cherrypy.response.headerMap["Content-Length"] = 39
        def inner():
            yield "hello"
            raise ValueError
            yield "very oops"
        return inner()
    
    def cause_err_in_finalize(self):
        # Since status must start with an int, this should error.
        cherrypy.response.status = "ZOO OK"


class Headers(Test):
    
    def index(self):
        # From http://www.cherrypy.org/ticket/165:
        # "header field names should not be case sensitive sayes the rfc.
        # if i set a headerfield in complete lowercase i end up with two
        # header fields, one in lowercase, the other in mixed-case."
        
        # Set the most common headers
        hMap = cherrypy.response.headerMap
        hMap['content-type'] = "text/html"
        hMap['content-length'] = 18
        hMap['server'] = 'CherryPy headertest'
        hMap['location'] = ('%s://127.0.0.1:8000/headers/'
                            % cherrypy.request.scheme)
        
        # Set a rare header for fun
        hMap['Expires'] = 'Thu, 01 Dec 2194 16:00:00 GMT'
        
        return "double header test"


defined_http_methods = ("OPTIONS", "GET", "HEAD", "POST", "PUT", "DELETE",
                        "TRACE", "CONNECT")
class Method(Test):
    
    def index(self):
        m = cherrypy.request.method
        if m in defined_http_methods:
            return m
        
        if m == "LINK":
            cherrypy.response.status = 405
        else:
            cherrypy.response.status = 501
    
    def parameterized(self, data):
        return data
    
    def request_body(self):
        # This should be a file object (temp file),
        # which CP will just pipe back out if we tell it to.
        return cherrypy.request.body


class Cookies(Test):
    
    def single(self, name):
        cookie = cherrypy.request.simpleCookie[name]
        cherrypy.response.simpleCookie[name] = cookie.value
    
    def multiple(self, names):
        for name in names:
            cookie = cherrypy.request.simpleCookie[name]
            cherrypy.response.simpleCookie[name] = cookie.value


cherrypy.config.update({
    'global': {
        'server.logToScreen': False,
        'server.environment': 'production',
        'foo': 'this',
        'bar': 'that',
    },
    '/foo': {
        'foo': 'this2',
        'baz': 'that2',
    },
    '/foo/bar': {
        'foo': 'this3',
        'bax': 'this4',
    },
})

import helper
import os

class CoreRequestHandlingTest(helper.CPWebCase):
    
    def testConfig(self):
        tests = [
            ('/',        'nex', None   ),
            ('/',        'foo', 'this' ),
            ('/',        'bar', 'that' ),
            ('/xyz',     'foo', 'this' ),
            ('/foo',     'foo', 'this2'),
            ('/foo',     'bar', 'that' ),
            ('/foo',     'bax', None   ),
            ('/foo/bar', 'baz', 'that2'),
            ('/foo/nex', 'baz', 'that2'),
        ]
        for path, key, expected in tests:
            cherrypy.request.path = path
            result = cherrypy.config.get(key, None)
            self.assertEqual(result, expected)
    
    def testParams(self):
        self.getPage("/params/?thing=a")
        self.assertBody('a')
        
        self.getPage("/params/?thing=a&thing=b&thing=c")
        self.assertBody('abc')
    
    def testStatus(self):
        self.getPage("/status/")
        self.assertBody('normal')
        self.assertStatus('200 OK')
        
        self.getPage("/status/blank")
        self.assertBody('')
        self.assertStatus('200 OK')
        
        self.getPage("/status/illegal")
        self.assertBody('oops' + (" " * 509))
        self.assertStatus('500 Internal error')
        
        self.getPage("/status/unknown")
        self.assertBody('funky')
        self.assertStatus('431 My custom error')
        
        self.getPage("/status/bad")
        self.assertBody('hello' + (" " * 508))
        self.assertStatus('500 Internal error')
    
    def testRedirect(self):
        self.getPage("/redirect/")
        self.assertBody('child')
        self.assertStatus('200 OK')
        
        self.getPage("/redirect?id=3")
        self.assert_(self.status in ('302 Found', '303 See Other'))
        self.assertInBody("<a href='http://127.0.0.1:8000/redirect/?id=3'>"
                          "http://127.0.0.1:8000/redirect/?id=3</a>")
        
        self.getPage("/redirect/by_code?code=300")
        self.assertInBody("<a href='somewhere else'>somewhere else</a>")
        self.assertStatus('300 Multiple Choices')
        
        self.getPage("/redirect/by_code?code=301")
        self.assertInBody("<a href='somewhere else'>somewhere else</a>")
        self.assertStatus('301 Moved Permanently')
        
        self.getPage("/redirect/by_code?code=302")
        self.assertInBody("<a href='somewhere else'>somewhere else</a>")
        self.assertStatus('302 Found')
        
        self.getPage("/redirect/by_code?code=303")
        self.assertInBody("<a href='somewhere else'>somewhere else</a>")
        self.assertStatus('303 See Other')
        
        self.getPage("/redirect/by_code?code=307")
        self.assertInBody("<a href='somewhere else'>somewhere else</a>")
        self.assertStatus('307 Temporary Redirect')
        
        self.getPage("/redirect/nomodify")
        self.assertBody('')
        self.assertStatus('304 Not modified')
        
        self.getPage("/redirect/proxy")
        self.assertBody('')
        self.assertStatus('305 Use Proxy')
        
        # InternalRedirect
        self.getPage("/redirect/internal")
        self.assertBody('hello')
        self.assertStatus('200 OK')
        
        self.getPage("/redirect/internal2?user_id=Sir-not-appearing-in-this-film")
        self.assertBody('0 images for Sir-not-appearing-in-this-film')
        self.assertStatus('200 OK')
        
        self.getPage("/redirect/internal2?user_id=parrot")
        self.assertBody('0 images for slug')
        self.assertStatus('200 OK')
        
        self.getPage("/redirect/internal2?user_id=terrier")
        self.assertBody('0 images for fish')
        self.assertStatus('200 OK')
    
    def testFlatten(self):
        for url in ["/flatten/as_string", "/flatten/as_list",
                    "/flatten/as_yield", "/flatten/as_dblyield",
                    "/flatten/as_refyield"]:
            self.getPage(url)
            self.assertBody('content')
    
    def testErrorHandling(self):
        self.getPage("/error/missing")
        self.assertStatus("404 Not Found")
        self.assertInBody("NotFound")
        
        ignore = helper.webtest.ignored_exceptions
        ignore.append(ValueError)
        try:
            valerr = r'\n    raise ValueError\nValueError\n$'
            self.getPage("/error/page_method")
            self.assertMatchesBody(valerr)
            
            import cherrypy
            proto = cherrypy.config.get("server.protocolVersion", "HTTP/1.0")
            if proto == "HTTP/1.1":
                valerr = r'Unrecoverable error in the server.$'
            self.getPage("/error/page_yield")
            self.assertMatchesBody(valerr)
            
            if cherrypy._httpserver is None and proto == "HTTP/1.0":
                self.assertRaises(ValueError, self.getPage, "/error/page_http_1_1")
            else:
                self.getPage("/error/page_http_1_1")
                # Because this error is raised after the response body has
                # started, the status should not change to an error status.
                self.assertStatus("200 OK")
                self.assertBody("helloUnrecoverable error in the server.")
            
            self.getPage("/error/cause_err_in_finalize")
            # We're in 'production' mode, so body should be empty
            self.assertBody("")
        finally:
            ignore.pop()
    
    def testHeaderCaseSensitivity(self):
        # Tests that each header only appears once, regardless of case.
        self.getPage("/headers/")
        self.assertBody("double header test")
        hnames = [name.title() for name, val in self.headers]
        for key in ['Content-Length', 'Content-Type', 'Date',
                    'Expires', 'Location', 'Server']:
            self.assertEqual(hnames.count(key), 1)
    
    def testHTTPMethods(self):
        # Test that all defined HTTP methods work.
        for m in defined_http_methods:
            h = []
            self.getPage("/method/", method=m)
            
            # HEAD requests should not return any body.
            if m == "HEAD":
                m = ""
            
            self.assertBody(m)
        
        # Request a PUT method with a form-urlencoded body
        self.getPage("/method/parameterized", method="PUT",
                       body="data=on+top+of+other+things")
        self.assertBody("on top of other things")
        
        # Request a PUT method with a file body
        h = [("Content-type", "text/plain"),
             ("Content-Length", "27")]
        
        self.getPage("/method/request_body", headers=h, method="PUT",
                       body="one thing on top of another")
        self.assertBody("one thing on top of another")
        
        # Request a disallowed method
        self.getPage("/method/", method="LINK")
        self.assertStatus("405 Method Not Allowed")
        
        # Request an unknown method
        self.getPage("/method/", method="SEARCH")
        self.assertStatus("501 Not Implemented")
    
    def testFavicon(self):
        # Calls to favicon.ico are special-cased in _cphttptools.
        localDir = os.path.dirname(__file__)
        icofilename = os.path.join(localDir, "../favicon.ico")
        icofile = open(icofilename, "rb")
        data = icofile.read()
        icofile.close()
        
        self.getPage("/favicon.ico")
        self.assertBody(data)
        
        self.getPage("/redirect/favicon.ico")
        self.assertBody(data)
    
    def testCookies(self):
        self.getPage("/cookies/single?name=First",
                     [('Cookie', 'First=Dinsdale;')])
        self.assertHeader('Set-Cookie', 'First=Dinsdale;')
        
        self.getPage("/cookies/multiple?names=First&names=Last",
                     [('Cookie', 'First=Dinsdale; Last=Piranha;'),
                      ])
        self.assertHeader('Set-Cookie', 'First=Dinsdale;')
        self.assertHeader('Set-Cookie', 'Last=Piranha;')


if __name__ == '__main__':
    helper.testmain()
