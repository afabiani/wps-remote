# (c) 2016 Open Source Geospatial Foundation - all rights reserved
# (c) 2014 - 2015 Centre for Maritime Research and Experimentation (CMRE)
# (c) 2013 - 2014 German Aerospace Center (DLR)
# This code is licensed under the GPL 2.0 license, available at the root
# application directory.

import unittest

import input_parameters
import command_line_parameter
import path
import urllib
import pickle


class Test(unittest.TestCase):
    
    def test_parse_two_int_par(self):
        paramsDef = [('argx', {"type": "int", "description": "descr of argx", "max": 2, "template" : "--name=value"}) ] 
        paramValue = {'argx' : ["1","2"] }

        pip = input_parameters.InputParameters(paramsDef)
        pip.parse( paramValue )

        self.assertEquals(pip.get_cmd_line(), "--argx=1 --argx=2 ")

    def test_parse_two_string_par(self):
        paramsDef = [('argX', {"type": "string", "description": "descr of argx", "max": 2, "template" : "--name=value"}) ] 
        paramValue = {'argX' : ["aaa","b"] }

        pip = input_parameters.InputParameters(paramsDef)
        pip.parse( paramValue )
        res = pip.get_cmd_line()

        self.assertEquals(res, "--argX=aaa --argX=b ")

    def test_parse_wrog_type(self):
        paramsDef = [('argx', {"type": "int", "description": "descr of argx", "max": 1, "template" : "--name=value"}) ] 
        paramValue = {'argx' : '1bubu00' }

        pip = input_parameters.InputParameters(paramsDef)
        self.assertRaises( Exception, pip.parse, paramValue)

    def test_parse_float_par_with_alias(self):
        paramsDef = [('argx', {"type": "float", "description": "descr of argx", "max": 1, "template" : "--name=value", "alias": "arg_alias"}) ] 
        paramValue = {'argx' : '5.234' }


        pip = input_parameters.InputParameters(paramsDef)
        pip.parse( paramValue )
        res = pip.get_cmd_line()

        self.assertEquals(res, "--arg_alias=5.234 " )


    def test_parse_const_cmdline_par(self):
        paramsDef = [('argx', {"type": "string", "description": "descr of argx", "max": 1, "template" : "value", "value" : "this should be used", "class" : "command_line_parameter.CommandLineParameterConst" }) ] 
        
        pip = input_parameters.InputParameters(paramsDef)
        #pip.parse( paramValue ) #parse ins not becessary because there is only one CommandLineParameterConst
        self.assertEquals(pip.get_cmd_line().strip(), "this should be used" )
    



if __name__ == '__main__':
    unittest.main()