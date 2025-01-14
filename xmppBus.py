# (c) 2016 Open Source Geospatial Foundation - all rights reserved
# (c) 2014 - 2015 Centre for Maritime Research and Experimentation (CMRE)
# (c) 2013 - 2014 German Aerospace Center (DLR)
# This code is licensed under the GPL 2.0 license, available at the root
# application directory.

import socket
import logging
import urllib
import pickle
import sleekxmpp
import busIndipendentMessages
import xmppMessages
import bus

class XMPPBus(bus.Bus):
    def __init__(self, config, service_name, service_name_namespace, id="master"):
        bus.Bus.__init__(self, id)
        

        self.config=config
        self.address=(config.get("DEFAULT", "address"), config.get("DEFAULT", "port")) # As address use mnemonic names
        self.domain = config.get("DEFAULT", "domain") #"whale.nurc.nato.int"
        self.MUC_name = config.get("DEFAULT", "mucService")
        self.password=config.get("DEFAULT", "password") #'Crociera100!'
        self.nameSpacePassword = config.get("DEFAULT", "mucServicePassword") #"admin"
        
        self._service_name = service_name
        self._service_name_namespace = service_name_namespace
        self._fully_qualified_service_name = self._service_name_namespace + "." + self._service_name

        self.xmpp = sleekxmpp.ClientXMPP(self._get_JId(), self.password)
        self.xmpp.register_plugin('xep_0004') # Data forms
        self.xmpp.register_plugin('xep_0030') # Service Discovery
        self.xmpp.register_plugin('xep_0045') # MUC
        self.xmpp.register_plugin('xep_0060') # MUC
        self.xmpp.register_plugin('xep_0077') # In-band Registration
        self.xmpp.register_plugin('xep_0078') # Non-SASL Authentication
        self.xmpp.register_plugin('xep_0199') # XMPP Ping
        self.xmpp.register_plugin('xep_0249') # Direct MUC invitation
        self.xmpp.add_event_handler('register', self._register)
        self.xmpp.add_event_handler('session_start', self._startService)
        self.xmpp.add_event_handler('message', self._handleXMPPSignal)


    def clone_for_process(self, id):
        c=XMPPBus(self.config, self._service_name, self._service_name_namespace, id)
        return c


    def _get_JId(self):
        #default.Service@whale.nurc.nato.int/master@WW717962
        return ''.join([self._fully_qualified_service_name, '@', self.domain, '/', self.id, '@', socket.gethostname()])

    def _get_MUC_JId(self):
        return self._service_name_namespace + "@" + self.MUC_name

    def _MUC_service_nickname(self):
        return '%s@%s' % (self._service_name, str(self.xmpp.boundjid).split('@', 1).pop())  


    def CheckServerIdentity(self, serverId):
        pass

    def get_fully_qualified_service_name(self):
        return self._fully_qualified_service_name

    def Listen(self):
        if self.xmpp.connect(self.address, use_tls=False, use_ssl=True):
            self.xmpp.process(block=True)
        else:
            print "Cannot connect to xmpp server"

    def _startService(self, event):
        #once the connection is established, immidiatelly join the MUC, no notification is sent to the calling class (serviceBot and processBot)
        self.JoinMUC()

    def JoinMUC(self):
        self.xmpp.plugin['xep_0045'].joinMUC(self._get_MUC_JId(), self._MUC_service_nickname(), password=self.nameSpacePassword)

    def _handleXMPPSignal(self, msg):
        imsg=self.CreateIndipendentMessage(msg)
        if (imsg is not None):
            self.callbacks[type(imsg)](imsg)

    def CreateIndipendentMessage(self, msg):
        if msg['type'] in ('normal', 'chat'):
            payload = msg['body'] 
            origin = msg['from']

            logging.info('Received XMPP bus signal from %s: "%s"' % (origin, payload))

            #todo: check for role=moderator
            role = 'visitor'
            roster = self.xmpp.plugin['xep_0045'].getRoster(self._get_MUC_JId())
            if origin.resource in roster:
                role = self.xmpp.plugin['xep_0045'].rooms[self._get_MUC_JId()][origin.resource]['role']
            elif origin.user in roster:
                role = self.xmpp.plugin['xep_0045'].rooms[self._get_MUC_JId()][origin.user]['role']

            if role == 'moderator':
                if ("topic=request" in payload):
                    variables = dict([tuple(each.strip().split('=')) for each in payload.split('&')])
                    requestParams=pickle.loads(urllib.unquote(variables['message'])) if variables['message'] is not None else None
                    #print str(variables)
                    return busIndipendentMessages.ExecuteMessage( msg['from'], variables['id'], variables['baseURL'], requestParams )  
                elif ("topic=invite" in payload):
                    return busIndipendentMessages.InviteMessage(payload, msg['from'])
                elif ("topic=finish" in payload):
                    return busIndipendentMessages.FinishMessage(payload, msg['from'])
                else:
                    pass
        return None

    def SendMessage(self, message):
        m=self.Convert(message)
        m.send()

    def Stop(self, Message):
        pass

    def _register(self, iq):
        pass

    def Convert(self, busIndipendentMsg):
        if (type(busIndipendentMsg) is busIndipendentMessages.RegisterMessage):
            return xmppMessages.XMPPRegisterMessage(self, busIndipendentMsg.originator(), busIndipendentMsg.service, busIndipendentMsg.namespace, busIndipendentMsg.description, busIndipendentMsg.input_parameters(), busIndipendentMsg.output)
        
        if (type(busIndipendentMsg) is busIndipendentMessages.ProgressMessage):
            return xmppMessages.XMPPProgressMessage(  busIndipendentMsg.originator, self, busIndipendentMsg.progress )
        
        if (type(busIndipendentMsg) is busIndipendentMessages.LogMessage):
            return xmppMessages.XMPPLogMessage(busIndipendentMsg.originator, self, busIndipendentMsg.level, busIndipendentMsg.msg)

        if (type(busIndipendentMsg) is busIndipendentMessages.CompletedMessage):
            return xmppMessages.XMPPCompletedMessage(busIndipendentMsg.originator, self, busIndipendentMsg.base_url, busIndipendentMsg.outputs() )

        if (type(busIndipendentMsg) is busIndipendentMessages.ErrorMessage):
            return xmppMessages.XMPPErrorMessage(busIndipendentMsg.originator, self, busIndipendentMsg.msg)

        else:
            raise Exception("unknown message")


    def disconnect(self):
        self.xmpp.disconnect(wait=True)
    
    def state(self):
        return self.xmpp.state.current_state()
