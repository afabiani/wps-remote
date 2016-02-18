# (c) 2016 Open Source Geospatial Foundation - all rights reserved
# (c) 2014 - 2015 Centre for Maritime Research and Experimentation (CMRE)
# (c) 2013 - 2014 German Aerospace Center (DLR)
# This code is licensed under the GPL 2.0 license, available at the root
# application directory.


import computation_job_input

class ComputationJobConst(computation_job_input.ComputationJobInput):

    def __init__(self, name, input_type, title, descr, value):
        super(ComputationJobConst, self).__init__(name, input_type, title, descr)
        self.set_value( value)

