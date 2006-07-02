import test
test.prefer_parent_path()

import threading

import cherrypy


class Root:
    def index(self):
        return "Hello World"
    index.exposed = True
    
    def ctrlc(self):
        raise KeyboardInterrupt()
    ctrlc.exposed = True
    
    def restart(self):
        cherrypy.engine.restart()
        return "app was restarted succesfully"
    restart.exposed = True

cherrypy.tree.mount(Root())
cherrypy.config.update({
    'log_to_screen': False,
    'environment': 'production',
    })

class Dependency:
    
    def __init__(self):
        self.running = False
        self.startcount = 0
        self.threads = {}
    
    def start(self):
        self.running = True
        self.startcount += 1
    
    def stop(self):
        self.running = False
    
    def startthread(self, thread_id):
        self.threads[thread_id] = None
    
    def stopthread(self, thread_id):
        del self.threads[thread_id]


import helper

class ServerStateTests(helper.CPWebCase):
    
    def test_0_NormalStateFlow(self):
        if not self.server_class:
            # Without having called "cherrypy.engine.start()", we should
            # get a 503 Service Unavailable response.
            self.getPage("/")
            self.assertStatus(503)
        
        # And our db_connection should not be running
        self.assertEqual(db_connection.running, False)
        self.assertEqual(db_connection.startcount, 0)
        self.assertEqual(len(db_connection.threads), 0)
        
        # Test server start
        cherrypy.server.start(self.server_class)
        cherrypy.engine.start(blocking=False)
        self.assertEqual(cherrypy.engine.state, 1)
        
        if self.server_class:
            host = cherrypy.config.get('server.socket_host')
            port = cherrypy.config.get('server.socket_port')
            self.assertRaises(IOError, cherrypy._cpserver.check_port, host, port)
        
        # The db_connection should be running now
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.startcount, 1)
        self.assertEqual(len(db_connection.threads), 0)
        
        self.getPage("/")
        self.assertBody("Hello World")
        self.assertEqual(len(db_connection.threads), 1)
        
        # Test engine stop
        cherrypy.engine.stop()
        self.assertEqual(cherrypy.engine.state, 0)
        
        # Verify that the on_stop_engine function was called
        self.assertEqual(db_connection.running, False)
        self.assertEqual(len(db_connection.threads), 0)
        
        if not self.server_class:
            # Once the engine has stopped, we should get a 503
            # error again. (If we were running an HTTP server,
            # then the connection should not even be processed).
            self.getPage("/")
            self.assertStatus(503)
        
        # Block the main thread now and verify that stop() works.
        def stoptest():
            self.getPage("/")
            self.assertBody("Hello World")
            cherrypy.engine.stop()
        cherrypy.engine.start_with_callback(stoptest)
        self.assertEqual(cherrypy.engine.state, 0)
        cherrypy.server.stop()
    
    def test_1_Restart(self):
        cherrypy.server.start(self.server_class)
        cherrypy.engine.start(blocking=False)
        
        # The db_connection should be running now
        self.assertEqual(db_connection.running, True)
        sc = db_connection.startcount
        
        self.getPage("/")
        self.assertBody("Hello World")
        self.assertEqual(len(db_connection.threads), 1)
        
        # Test server restart from this thread
        cherrypy.engine.restart()
        self.assertEqual(cherrypy.engine.state, 1)
        self.getPage("/")
        self.assertBody("Hello World")
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.startcount, sc + 1)
        self.assertEqual(len(db_connection.threads), 1)
        
        # Test server restart from inside a page handler
        self.getPage("/restart")
        self.assertEqual(cherrypy.engine.state, 1)
        self.assertBody("app was restarted succesfully")
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.startcount, sc + 2)
        # Since we are requesting synchronously, is only one thread used?
        # Note that the "/restart" request has been flushed.
        self.assertEqual(len(db_connection.threads), 0)
        
        cherrypy.engine.stop()
        self.assertEqual(cherrypy.engine.state, 0)
        self.assertEqual(db_connection.running, False)
        self.assertEqual(len(db_connection.threads), 0)
        cherrypy.server.stop()
    
    def test_2_KeyboardInterrupt(self):
        if self.server_class:
            
            # Raise a keyboard interrupt in the HTTP server's main thread.
            def interrupt():
                cherrypy.server.wait()
                cherrypy.server.httpserver.interrupt = KeyboardInterrupt
            threading.Thread(target=interrupt).start()
            
            # We must start the server in this, the main thread
            cherrypy.server.start(self.server_class)
            # Time passes...
            self.assertEqual(db_connection.running, False)
            self.assertEqual(len(db_connection.threads), 0)
            
            # Raise a keyboard interrupt in a page handler; on multithreaded
            # servers, this should occur in one of the worker threads.
            # This should raise a BadStatusLine error, since the worker
            # thread will just die without writing a response.
            def interrupt():
                cherrypy.server.wait()
                from httplib import BadStatusLine
                self.assertRaises(BadStatusLine, self.getPage, "/ctrlc")
            threading.Thread(target=interrupt).start()
            
            cherrypy.server.start(self.server_class)
            # Time passes...
            self.assertEqual(db_connection.running, False)
            self.assertEqual(len(db_connection.threads), 0)


db_connection = None

def run(server, conf):
    helper.setConfig(conf)
    ServerStateTests.server_class = server
    suite = helper.CPTestLoader.loadTestsFromTestCase(ServerStateTests)
    try:
        global db_connection
        db_connection = Dependency()
        cherrypy.engine.on_start_engine_list.append(db_connection.start)
        cherrypy.engine.on_stop_engine_list.append(db_connection.stop)
        cherrypy.engine.on_start_thread_list.append(db_connection.startthread)
        cherrypy.engine.on_stop_thread_list.append(db_connection.stopthread)
        
        helper.CPTestRunner.run(suite)
    finally:
        cherrypy.server.stop()
        cherrypy.engine.stop()


def run_all(host, port):
    conf = {'server.socket_host': host,
            'server.socket_port': port,
            'server.thread_pool': 10,
            'log_to_screen': False,
            'log_config': False,
            'environment': "production",
            'show_tracebacks': True,
            }
    def _run(server):
        print
        print "Testing %s on %s:%s..." % (server, host, port)
        run(server, conf)
    _run("cherrypy._cpwsgi.WSGIServer")


def run_localhosts(port):
    for host in ("", "127.0.0.1", "localhost"):
        conf = {'server.socket_host': host,
                'server.socket_port': port,
                'server.thread_pool': 10,
                'log_to_screen': False,
                'log_config': False,
                'environment': "production",
                'show_tracebacks': True,
                }
        def _run(server):
            print
            print "Testing %s on %s:%s..." % (server, host, port)
            run(server, conf)
        _run("cherrypy._cpwsgi.WSGIServer")


if __name__ == "__main__":
    import sys
    host = '127.0.0.1'
    port = 8000
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in [prefix + atom for atom in ("?", "h", "help")
                   for prefix in ("", "-", "--", "\\")]:
            print
            print "test_states.py -?             -> this help page"
            print "test_states.py [host] [port]  -> run the tests on the given host/port"
            print "test_states.py -localhosts [port]  -> try various localhost strings"
            sys.exit(0)
        if len(sys.argv) > 2:
            port = int(sys.argv[2])
        if cmd == "-localhosts":
            run_localhosts(port)
            sys.exit(0)
        host = sys.argv[1].strip("\"'")
    run_all(host, port)
