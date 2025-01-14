# (c) 2016 Open Source Geospatial Foundation - all rights reserved
# (c) 2014 - 2015 Centre for Maritime Research and Experimentation (CMRE)
# (c) 2013 - 2014 German Aerospace Center (DLR)
# This code is licensed under the GPL 2.0 license, available at the root
# application directory.

import introspection
import thread
from collections import OrderedDict
import tempfile
import subprocess
import datetime
import logging

import busIndipendentMessages

import configInstance
import computation_job_inputs
import output_parameters
import resource_cleaner

class ServiceBot(object):
    """This script is the remote WPS agent. One instance of this agent runs on each computational node connected to the WPS for each algorithm available. The script runs continuosly.
    """
    def __init__(self, remote_config_filepath, service_config_filepath):

        #read remote config file
        self._remote_config_filepath = remote_config_filepath
        remote_config = configInstance.create(self._remote_config_filepath)
        bus_class_name = remote_config.get("DEFAULT", "bus_class_name") #identify the class implementation of the cominication bus
        self._resource_file_dir = remote_config.get_path("DEFAULT", "resource_file_dir") # directory used to store file for resource cleaner
        if remote_config.has_option("DEFAULT", "wps_execution_shared_dir"):
            self._wps_execution_shared_dir = remote_config.get_path("DEFAULT", "wps_execution_shared_dir") # directory used to store the process encoded outputs (usually on a shared fs)

            #ensure outdir exists
            if not self._wps_execution_shared_dir.exists():
                self._wps_execution_shared_dir.mkdir()
        else:
            self._wps_execution_shared_dir = None

        #read service config, with raw=true that is without config file's value interpolation. Interpolation values are prodice only for the process bot (request hanlder); for example the unique execution id value to craete the sand box directory
        self._service_config_file = service_config_filepath
        serviceConfig = configInstance.create(service_config_filepath, case_sensitive=True, variables = {'wps_execution_shared_dir' : self._wps_execution_shared_dir}, raw=True)
        self.service = serviceConfig.get("DEFAULT", "service") #WPS service name?
        self.namespace = serviceConfig.get("DEFAULT", "namespace")
        self.description = serviceConfig.get("DEFAULT", "description") #WPS service description
        self._active = serviceConfig.get("DEFAULT", "active").lower() == "true" #True
        self._output_dir =  serviceConfig.get_path("DEFAULT", "output_dir") 
        self._max_running_time = datetime.timedelta( seconds = serviceConfig.getint("DEFAULT", "max_running_time_seconds") )

        input_sections = OrderedDict()
        for input_section in [s for s in serviceConfig.sections() if 'input' in s.lower() or 'const' in s.lower()]:
            #service bot doesn't have yet the execution unique id, thus the serviceConfig is read with raw=True to avoid config file variables interpolation 
            input_sections[input_section] = serviceConfig.items_without_defaults(input_section, raw=True)
        self._input_parameters_defs = computation_job_inputs.ComputationJobInputs.create_from_config( input_sections )

        output_sections=OrderedDict()
        for output_section in [s for s in serviceConfig.sections() if 'output' in s.lower()]:
            output_sections[output_section] = serviceConfig.items_without_defaults(output_section, raw=True)
        self._output_parameters_defs = output_parameters.OutputParameters.create_from_config( output_sections, self._wps_execution_shared_dir )
        
        #create the concrete bus object
        self.bus = introspection.get_class_three_arg(bus_class_name, remote_config, self.service, self.namespace)

        self.bus.RegisterMessageCallback(busIndipendentMessages.InviteMessage, self.handle_invite) 
        self.bus.RegisterMessageCallback(busIndipendentMessages.ExecuteMessage, self.handle_execute)
        
        #self._lock_running_process =  thread.allocate_lock() #critical section to access running_process from separate threads
        self.running_process={}

        self._redirect_process_stdout_to_logger = False #send the process bot (aka request handler) stdout to service bot (remote wps agent) log file
        self._remote_wps_endpoint = None

    def get_resource_file_dir(self):
        return self._resource_file_dir

    def get_wps_execution_shared_dir(self):
        return self._wps_execution_shared_dir

    def max_execution_time(self):
        return self._max_running_time

    def run(self):
        logger = logging.getLogger("servicebot.run")
        if self._active:
            logger.info("Start listening on bus")
            self.bus.Listen()
        else:
            logger.error("This service is disabled, exit process")
            return 

    def handle_invite(self, invite_message):
        """Handler for WPS invite message."""
        logger = logging.getLogger("servicebot.handle_execute")
        logger.info("handle invite message from WPS " + str(invite_message.originator()))
        self.bus.SendMessage(
            busIndipendentMessages.RegisterMessage(invite_message.originator(), 
                                                   self.service, 
                                                   self.namespace, 
                                                   self.description, 
                                                   self._input_parameters_defs.as_DLR_protocol(), 
                                                   self._output_parameters_defs.as_DLR_protocol()
                                                   )
        )

    def handle_execute(self, execute_message):
        """Handler for WPS execute message."""
        logger = logging.getLogger("servicebot.handle_execute")

        #save execute messsage to tmmp file to enable the process bot to read the inputs
        tmp_file = tempfile.NamedTemporaryFile(prefix='wps_params_', suffix=".tmp", delete=False)
        execute_message.serialize( tmp_file )
        param_filepath = tmp_file.name
        tmp_file.close()
        logger.debug("save parameters file for executing process " + self.service+  " in " + param_filepath)

        #create the Resource Cleaner file containing the process info. The "invoked_process.pid" will be set by the spawned process itself

        r = resource_cleaner.Resource()
        #create a resource... 
        r.set_from_servicebot(execute_message.UniqueId(), self._output_dir / execute_message.UniqueId())
        #... and save to file
        r.write()

        #invoke the process bot (aka request handler) asynchronously
        cmd = 'python wpsagent.py -r ' + self._remote_config_filepath + ' -s ' + self._service_config_file + ' -p ' + param_filepath + ' process'
        invoked_process = subprocess.Popen(args=cmd.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        logger.info("created process " + self.service +  " with PId " + str(invoked_process.pid) + " and cmd: " + cmd )
        
        #use a parallel thread to wait the end of the request handler process and get the exit code of the just created asynchronous process computation 
        thread.start_new_thread(self.output_parser_verbose, (invoked_process,))

        logger.info("end of execute message handler, going back in listening mode")

    def output_parser(self, invoked_process):
        #silently wait the end of the computaion
        logger = logging.getLogger("servicebot.output_parser")
        return_code = invoked_process.wait()
        logger.info("Process " + self.service +  " PId " + str(invoked_process.pid)  + " terminated with exit code " + str(return_code) )

    def output_parser_verbose(self, invoked_process):
        logger = logging.getLogger("servicebot.output_parser_verbose")
        logger.info("wait for end of execution of created process " + self.service +  ", PId " + str(invoked_process.pid) )
        while True:
            line = invoked_process.stdout.readline()
            if line != '':
                if self._redirect_process_stdout_to_logger:
                    line = line.strip()
                    logger.debug("[SERVICE] " + line)
            else:
                logger.debug("created process " + self.service +  ", PId " + str(invoked_process.pid) + " stopped send data on stdout")
                break #end of stream

        #wait for process exit code
        return_code = invoked_process.wait()
        logger.info("Process " + self.service +  " PId " + str(invoked_process.pid)  + " terminated with exit code " + str(return_code) )

    def send_error_message(self, msg):
        logger = logging.getLogger("ServiceBot.send_error_message")
        logger.error( msg ) 
        self.bus.SendMessage( busIndipendentMessages.ErrorMessage(  self._remote_wps_endpoint, msg ) )

    def disconnect(self):
        self.bus.disconnect()
