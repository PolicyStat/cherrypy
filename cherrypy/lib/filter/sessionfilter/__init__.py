import time

import cherrypy

import sessionconfig

from sessionerrors import SessionNotFoundError, SessionIncompatibleError, SessionBadStorageTypeError, SessionConfigError
from ramadaptor import RamSession
from fileadaptor import FileSession
from anydbadaptor import DBMSession

_sessionTypes = {
                  'ram'       : RamSession,
                  'file'      : FileSession,
                  'anydb'     : DBMSession
                }

try:
    # the user might not have sqlobject instaled
    from sqlobjectadaptor import SQLObjectSession
    _sessionTypes['sqlobject'] = SQLObjectSession
except ImportError:
    pass


class SessionFilter:
    """
    Input filter - get the sessionId (or generate a new one) and load up the session data
    """

    def __init__(self):
        """ Initilizes the session filter and creates cherrypy.sessions  """

        try:
            from threading import local
        except ImportError:
            from cherrypy._cpthreadinglocal import local
        
        # Create as sessions object for accessing session data
        cherrypy.sessions = local()
        
        self.__localData= local()
        
        self.sessionManagers = {}
        cherrypy.config.update(sessionconfig._sessionDefaults, setDefault = True)


    def __newSessionManager(self, sessionName, sessionPath):
        """ 
        Takes the name of a new session and its configuration path.
        Returns a storageAdaptor instance maching the configured storage type.
        If the storage type is not built in, it tries to use sessionFilter.storageAadaptors.
        If the storage type still can not be found, an exception is raised.
        """
        # look up the storage type or return the default
        storageType = sessionconfig.retrieve('storageType', sessionName)
        
        # try to initilize a built in session
        try:
            storageAdaptor = _sessionTypes[storageType]
        except KeyError:
            # the storageType is not built in
            
            # check for custom storage adaptors
            adaptors = cherrypy.config.get('sessionFilter.storageAdaptors')
            try:
                storageAdaptor = adaptors[storageType]
            except cherrypy.InternalError:
                # we couldn't find the session
                raise SessionBadStorageTypeError(storageType)
        
        return storageAdaptor(sessionName, sessionPath)        
        
    def __loadConfigData(self):
        try:
            path = cherrypy.request.path
        except AttributeError:
            path = "/"
            
        configMap = cherrypy.config.configMap
        
        self.__localData.config = {}
        for section, settings in configMap.iteritems():
            if section == 'global':
                section = '/'
            if path.startswith(section):
                for key, value in settings.iteritems():
                    if key.startswith('sessionFilter.'):
                        sectionData = self.__localData.config.setdefault(section, {})
                        keySplit = key.split('.')
                        if len(keySplit) == 2:
                            defaults = sectionData.setdefault(None, {})
                            defaults[keySplit[1]] = value
                        elif len(keySplit) == 3:
                            currentSession = sectionData.setdefault(keySplit[1], {})
                            currentSession[keySplit[2]] = value
        
        self.__activeSessions = []
        for path, sessions in self.__localData.config.iteritems():
            
            for session, sessionSettings in sessions.iteritems():
                if session == None:
                    # because i couldn't stand more tabs
                    continue
                try:
                    sessionManager = self.sessionManagers[session]
                except KeyError:
                    sessionManager = self.__newSessionManager(session, path)
                    self.sessionManagers[session] = sessionManager

                sessionManager.settings = sessionSettings.copy()

                self.__activeSessions.append(sessionManager)

    def __initSessions(self):
        
        # look up all of the session keys by cookie
        self.__loadConfigData()
        
        sessionKeys = self.getSessionKeys()

        for sessionManager in self.__activeSessions:
            sessionKey = sessionKeys.get(sessionManager.name, None)
            
            try:
               sessionManager.loadSession(sessionKey)
            except SessionNotFoundError:
               newKey = sessionManager.createSession()
               sessionManager.loadSession(newKey)
               
               self.setSessionKey(newKey, sessionManager) 
    
    def getSessionKeys(self):
        """ 
        Returns the all current sessionkeys as a dict
        """
        
        sessionKeys = {}
        
        for sessionManager in self.__activeSessions:
            sessionName = sessionManager.name
            cookieName  = sessionManager.cookieName

            try:
                sessionKeys[sessionName] = cherrypy.request.simpleCookie[cookieName].value
            except:
                sessionKeys[sessionName] = None
        return sessionKeys
      
    def setSessionKey(self, sessionKey, sessionManager):
        """ 
        Sets the session key in a cookie. 
        """
        
        sessionName = sessionManager.name
        cookieName  = sessionManager.cookieName
        
        
        # if we do not have a manually defined cookie path use path where the session
        # manager was defined
        cookiePath = sessionconfig.retrieve('cookiePath', sessionManager.name, sessionManager.path)
        timeout = sessionconfig.retrieve('timeout', sessionManager.name)
        
        cherrypy.response.simpleCookie[cookieName] = sessionKey
        cherrypy.response.simpleCookie[cookieName]['path'] = cookiePath
        cherrypy.response.simpleCookie[cookieName]['max-age'] = timeout*60
        
    def __saveSessions(self):
        
        for sessionManager in self.__activeSessions:
            sessionName = sessionManager.name
            
            sessionData = getattr(cherrypy.sessions, sessionName)
            sessionManager.commitCache(sessionData.key)
            sessionManager.cleanUpCache()
            
            
            now = time.time()
            if sessionManager.nextCleanUp < now:
                sessionManager.cleanUpOldSessions()
                cleanUpDelay = sessionconfig.retrieve('cleanUpDelay', sessionManager.name)
                sessionManager.nextCleanUp=now + cleanUpDelay * 60

        # this isn't needed but may be helpfull for debugging
#        self.configData = None
    
    def beforeMain(self):
        if (not cherrypy.config.get('staticFilter.on', False)
            and cherrypy.config.get('sessionFilter.on')):
           self.__initSessions()

    def beforeFinalize(self):
        if (not cherrypy.config.get('staticFilter.on', False)
            and cherrypy.config.get('sessionFilter.on')):
            self.__saveSessions()

    #this breaks a test case
    def beforeErrorResponse(self):
        # Still save session data
        if not cherrypy.config.get('staticFilter.on', False) and \
            cherrypy.config.get('sessionFilter.on'):
            self.__saveSessions()
