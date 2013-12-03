'''
Created on Sep 10, 2012
@author: Y. Le Maout
'''

# TODO : Validation of int & double

import BaseHTTPServer
from suds.wsse import Security, UsernameToken
from suds.client import Client
from urlparse import parse_qs, urlparse
import json, os
import logging
import traceback, time
from suds.sax.element import Element
from suds.xsd.doctor import ImportDoctor, Import

class WSIntrospectorHTTPServer(BaseHTTPServer.HTTPServer):
    DIRECTORIES_TO_PRELOAD = ["css", "js"]
    CONTENT_TYPE_MAP = {
             "js":"application/x-javascript",
             "css":"text/css",
             "png":"image/png",
             "gif":"image/gif"
    }

    def __init__(self, server_address, handler_class, config_file_name):
        BaseHTTPServer.HTTPServer.__init__(self, server_address, handler_class)
        self.ws_map = self.getConfiguration(config_file_name)
        self.ws_clients = {}
        self.services = {}
        self.types = {}
        self.ws_service_definitions = {}
        self.server_start_time = time.time()
        self.ready = False

        # For Warm-up infos
        self.ws_loading_id = 0
        self.ws_loading_name = ""
        self.ws_total_nb = len(self.ws_map)

        logging.info("Current directory '%s'" % os.getcwd())

    def getConfiguration(self, config_file_name):
        """
        Config file example :

        [WS_NAME]
        wsdl=http://host:port/ws_url?wsdl
        user=user
        password=password
        http.headers.count=1
        http.headers.0=key1:val1
        soap.headers.count=1
        soap.headers.0.prefix=ssn
        soap.headers.0.uri=uri:org.apache.cxf
        soap.headers.0.count=3
        soap.headers.0.0=key1:val1
        soap.headers.0.1=key2:val2
        soap.headers.0.2=key3:val3
        """
        import ConfigParser
        config = ConfigParser.ConfigParser()
        with open(config_file_name) as conf_file:
            config.readfp(conf_file)
        mConfig = {
                section:{
                         k:v for (k, v) in config.items(section)
                } for section in config.sections()
        }
        return mConfig

    def preloadServer(self):
        self.preloadResources()

        for ws_name in self.ws_map:
            self.ws_loading_name = ws_name
            self.preloadWS(ws_name)
            self.ws_loading_id += 1

        logging.info("Up, running now...")
        self.ready = True

    def preloadWS(self, ws_name):
        self.services[ws_name] = {}
        self.types[ws_name] = {}
        if not self.addWSClient(ws_name): return
        self.loadMethods(ws_name)
        self.loadTypes(ws_name)


    def removeWSFromMaps(self, ws_name):
        if ws_name in self.ws_clients: del self.ws_clients[ws_name]
        if ws_name in self.ws_service_definitions: del self.ws_service_definitions[ws_name]
        if ws_name in self.services: del self.services[ws_name]
        if ws_name in self.types: del self.types[ws_name]

    def getHTTPHeaders(self, ws_name):
        ws_map = self.ws_map[ws_name]
        if not "http.headers.count" in ws_map:
            return {}
        header_count = 0
        try:
            header_count = int(ws_map["http.headers.count"])
        except:
            return {}
        http_headers = {}
        for i in range(header_count):
            header_key = "http.headers.%d" % i
            try:
                header = ws_map[header_key].split(':')
                http_headers[header[0]] = header[1]
            except Exception, e:
                logging.warn("Unable to read header %d for WS '%s' : %s" % (i, ws_name, e))
        return http_headers

    def getSoapHeaders(self, ws_name):
        ws_map = self.ws_map[ws_name]
        if not "soap.headers.count" in ws_map:
            return {}
        header_count = 0
        try:
            header_count = int(ws_map["soap.headers.count"])
        except:
            return {}

        soap_headers = []
        for i in range(header_count):
            try:
                ssnns = (ws_map["soap.headers.%d.prefix" % i],
                         ws_map["soap.headers.%d.uri" % i   ])

                for prop_idx in range(int(ws_map["soap.headers.%d.count" % i])):
                    key_val = ws_map["soap.headers.%d.%d" % (i, prop_idx)].split(':')
                    soap_headers.append(Element(key_val[0], ns = ssnns).setText(key_val[1]))
            except Exception, e:
                logging.warn("Unable to read header %d for WS '%s' : %s" % (i, ws_name, e))
        return soap_headers

    def addWSClient(self, ws_name):
        ws_map = self.ws_map[ws_name]
        logging.info("Loading WS '%s' from '%s'" % (ws_name, ws_map["wsdl"]))

        import_list = []
        client_args = {'url':ws_map["wsdl"]}
        import_doctor_count = int(ws_map.get('import.doctor.count', 0))
        for i in range(import_doctor_count):
            import_list.append(Import(ws_map['import.doctor.%d' % i]))

        if len(import_list) > 0:
            client_args['doctor'] = ImportDoctor()
            for x in import_list:
                client_args['doctor'].add(x)

        if 'http_simple_auth_user' in ws_map and 'http_simple_auth_password' in ws_map:
            credentials = {'username' : ws_map['http_simple_auth_user'],
                           'password' : ws_map['http_simple_auth_password']}
            from suds.transport.https import HttpAuthenticated
            client_args['transport'] = HttpAuthenticated(**credentials)

        try:

            self.ws_clients[ws_name] = Client(**client_args)
            self.services[ws_name]["infos"] = {"wsdl":ws_map["wsdl"], "user":ws_map["user"]}

            # HTTP & Soap Headers
            self.ws_clients[ws_name].set_options(
                headers = self.getHTTPHeaders(ws_name),
                soapheaders = self.getSoapHeaders(ws_name)
            )
            if "user" in ws_map and "password" in ws_map:
                security = Security()
                token = UsernameToken(ws_map["user"], ws_map["password"])
                security.tokens.append(token)
                self.ws_clients[ws_name].set_options(wsse = security)

            if len(self.ws_clients[ws_name].sd) > 1:
                logging.warn("More than one service definition found. Some elements may be not displayed")

            self.ws_service_definitions[ws_name] = self.ws_clients[ws_name].sd[0]
        except Exception, e:
            logging.error("An exception occured while loading WS '%s', it won't be available" % ws_name)
            logging.exception(e)
            self.removeWSFromMaps(ws_name)
            return False
        return True

    def loadMethods(self, ws_name):
        # TODO : improve names & genericity
        self.services[ws_name]["methods"] = {
            str(method[0]) :
            {
               str(method_parameter[0]):
                            {
                              "type":str(method_parameter[1].type[0]) if method_parameter[1].type is not None else "ukn",
                              "nillable":method_parameter[1].nillable
                            } for method_parameter in method[1]
            } for method in self.ws_service_definitions[ws_name].ports[0][1]
        }

    def loadTypes(self, ws_name):
        m = {}
        for service_def in self.ws_clients[ws_name].sd:
            for service_type in service_def.types:

                m[service_type[0].name] = {}
                self.types[ws_name][service_type[0].name] = service_type[0]
                if service_type[0].restriction():
                    m[service_type[0].name] = {"type"   : "enumeration",
                                               "values" : [str(v.name) for v in service_type[0].rawchildren[0].rawchildren]}
                    continue
                if len(service_type[0].rawchildren) == 0:
                    continue
                for children in service_type[0].rawchildren[0]:
                    if children is None: continue
                    param_type = "string"
                    if children[0].type is not None:
                        param_type = str(children[0].type[0])
                    m[service_type[0].name][children[0].name] = {
                                                                 "type" : str(param_type),
                                                                 "nillable" : children[0].nillable,
                                                                 "tuple" : (children[0].max == "unbounded"),
                                                                }
        self.services[ws_name]["types"] = m

    def preloadResources(self):
        logging.info("Pre-loading resources from %s" % ','.join(WSIntrospectorHTTPServer.DIRECTORIES_TO_PRELOAD))
        self.resources = {}
        for directory in WSIntrospectorHTTPServer.DIRECTORIES_TO_PRELOAD:
            for root, dirs, files in os.walk(directory):  # @UnusedVariable
                for file_name in files:
                    full_file_name = os.path.join(root, file_name)
                    key = "/%s" % full_file_name.replace(os.sep, '/')
                    f = open(full_file_name, 'rb')
                    self.resources[key] = f.read()
                    logging.debug("PreLoaded : '%s'" % full_file_name)
                    f.close()

    def getAllServices(self):
        return json.dumps(self.services)

    @staticmethod
    def startServer(server_port, ws_map):
        wsTester = WSIntrospectorHTTPServer(('', server_port), WSIntrospectorHTTPHandler, ws_map)
        logging.info("Up, pre-loading...")
        import threading
        threading.Thread(target = wsTester.preloadServer).start()
        wsTester.serve_forever()

class WSIntrospectorHTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def log_error(self, format_log, *args):
        logging.error("%s - - [%s] %s" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format_log % args))

    def log_message(self, format_log, *args):
        logging.info("%s - - [%s] %s" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format_log % args))

    def log_debug(self, format_log, *args):
        logging.debug("%s - - [%s] %s" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format_log % args))

    def getETagForPath(self):
        if "get_all_services" in self.path or self.path == '/':
            return '"%s"' % self.server.server_start_time
        else:
            return '"%s"' % os.path.getmtime(self.path[1:])

    def ack(self, path = None):
        return_status = 200
        if not "call_ws" in path:
            sETag = self.getETagForPath()
            sClientETag = self.headers.get('If-None-Match')
            if sETag == sClientETag:
                return_status = 304
                self.send_response(return_status, "Not Modified")
            else:
                self.send_response(return_status)
            self.send_header('ETag', sETag)

            sPathExt = path[path.rfind('.') + 1:].lower()
            sType = WSIntrospectorHTTPServer.CONTENT_TYPE_MAP.get(sPathExt)
            if sType is not None:
                self.send_header("content-type", sType)
        else:
            self.send_response(200)
        self.end_headers()
        return return_status

    def loadFileFromPath(self):
        if self.path in self.server.resources:
            self.wfile.write(self.server.resources[self.path])
            self.log_message("Loaded resource from cache : '%s'" % self.path)
            return

        try:
            self.log_message("Resource is not in cache, will load it directly : '%s'" % self.path)
            with open(self.path[1:], 'r+b') as f:
                self.wfile.write(f.read())
        except Exception, e:
            self.log_error("Exception occurred while loading resource '%s' : %s" % (self.path[1:], str(e)))
            raise

    def buildComplexType(self, user_parameters, parameter_type, parameter_name, depth = 0):
        if depth > 10:
            logging.info("Maximum iteration reached while building complex type %s :\n%s"
                         % (parameter_type, traceback.extract_stack()))
            return None

        if user_parameters is None:
            return None

        ws_name = self.current_ws_name  # user_parameters["webservice_select"]
        if self.server.types[ws_name][parameter_type].restriction():
            return user_parameters.get(parameter_name, '')

        complex_type_name = self.server.ws_service_definitions[ws_name].xlate(self.server.types[ws_name][parameter_type])
        complex_object = self.server.ws_clients[ws_name].factory.create(complex_type_name)
        for complex_object_attribute in complex_object.__keylist__:
            attribute_value = None
            if parameter_name in user_parameters:
                attribute_value = user_parameters[parameter_name]

            if self.server.types[ws_name][parameter_type].get_child(complex_object_attribute)[0] is not None and self.server.types[ws_name][parameter_type].get_child(complex_object_attribute)[0].type is not None:
                attr_infos = self.server.types[ws_name][parameter_type].get_child(complex_object_attribute)[0]
                attr_type = attr_infos.type[0]
                if attr_type in self.server.services[ws_name]["types"]:
                    if isinstance(getattr(complex_object, complex_object_attribute), list):
                        attribute_value = []
                        for item_param in user_parameters:
                            attribute_value.append(self.buildComplexType(item_param, attr_type, parameter_name, depth + 1))
                    else:
                        attribute_value = self.buildComplexType(user_parameters[complex_object_attribute], attr_type, complex_object_attribute, depth + 1)
                elif complex_object_attribute in user_parameters:
                    attribute_value = user_parameters[complex_object_attribute]
                elif isinstance(getattr(complex_object, complex_object_attribute), list):
                    attribute_value = user_parameters
            elif complex_object_attribute in user_parameters:
                attribute_value = user_parameters[complex_object_attribute]
            if attribute_value is not None:
                setattr(complex_object, complex_object_attribute, attribute_value)
        return complex_object

    def callWebService(self, user_parameters):
        if "service_name_select" not in user_parameters:
            return "No method provided"

        service_name = user_parameters["service_name_select"]
        ws_name = user_parameters["webservice_select"]
        self.current_ws_name = ws_name
        try:
            kwargs = {}
            parameters = self.server.services[ws_name]["methods"][service_name].keys()
            for p in parameters:
                parameter_type = self.server.services[ws_name]["methods"][service_name][p]["type"]
                if parameter_type in self.server.services[ws_name]["types"]:
                    kwargs[p] = self.buildComplexType(user_parameters.get(p), parameter_type, p)
                else:
                    kwargs[p] = user_parameters.get(p, "")

            self.log_debug("Method : %s Arguments : %s " % (service_name, kwargs))
            ws_method = getattr(self.server.ws_clients[ws_name].service, service_name)
            if ("__request_type" in user_parameters and "simulate" in user_parameters["__request_type"]):
                # Simulation mode
                return ws_method.method.binding.input.get_message(ws_method.method, (), kwargs)
            else:
                return ws_method(**kwargs)
        except:
            return "Exception occurred : %s" % traceback.format_exc()

    def serveWaitingPage(self):
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.end_headers()
        self.wfile.write("""<head><meta http-equiv="Refresh" content="1"></head><div style="line-height: 115px; text-align: center;">""")
        self.wfile.write("<p>Please wait while server is warming up...</p>")
        self.wfile.write("<p>%d service(s) were loaded over %d</p>" % (self.server.ws_loading_id, self.server.ws_total_nb))
        self.wfile.write("<p>Currently loading : %s</p></div>" % self.server.ws_loading_name)

    def init_response(self):
        if not self.server.ready:
            self.serveWaitingPage()
            return False

        return self.ack(self.path) != 304

    def do_POST(self):
        if not self.init_response(): return

        if "call_ws" in self.path:
            content_len = int(self.headers.getheader('content-length'))
            post_body = self.rfile.read(content_len)
            query_dict = json.loads(post_body)
            result = self.callWebService(query_dict)
            self.log_message("Call to WS done (result has a size of %d). %s", len(str(result)), self.path)
            return self.wfile.write(result)

    def do_GET(self):
        if "favicon" in self.path: return
        if not self.init_response(): return

        if "/css/" in self.path or "/js/" in self.path:
            return self.loadFileFromPath()

        if "get_all_services" in self.path:
            return self.wfile.write(self.server.getAllServices())
        if "call_ws" in self.path:
            query_dict = parse_qs(urlparse(self.path).query)
            params = {k:query_dict[k][0] for k in query_dict.keys()}
            get_soap = "submit" in params and "simulate" in params["submit"]
            result = self.callWebService(params, get_soap)
            self.log_message("Call to WS done (result has a size of %d). %s", len(str(result)), self.path)
            return self.wfile.write(result)

        if self.path == "/":
            f = open("base.html")
            self.wfile.write(f.read())
            f.close()

if __name__ == '__main__':
    logging.basicConfig(level = logging.INFO                              ,
                        format = '%(levelname)s - %(asctime)s %(message)s',
                        datefmt = '%m/%d/%Y %I:%M:%S %p')
    WSIntrospectorHTTPServer.startServer(8484, "ws_config.ini")
