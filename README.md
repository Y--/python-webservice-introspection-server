python-webservice-introspection-server
======================================

A small Python HTTP server which allow to observe a WebService


Dependencies
======================================

Front-end :
--------------------------------------
* jQuery (tested with 1.9.1) http://jquery.com/
* jQuery UI (tested with 1.10.1) http://jqueryui.com/
* Dynatree (tested with 1.2.4) https://code.google.com/p/dynatree/
* autosize (tested with 1.13) http://www.jacklmoore.com/autosize/

Back-end (Python) :
--------------------------------------
* Python (tested with 2.7) http://www.python.org/
* Suds (tested with 0.4) https://fedorahosted.org/suds/

TODOs
======================================
* Migrate to AngularJS
* Migrate back-end to Node.JS
* Complete this list (haha)

Usage
======================================
Create a configuration file named `ws_config.ini` with all the WebService you would like to inspect, one per section.

Each sections should looks like :

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

Run the server as simply as :

    python ws_server.py

Point your favorite browser to [http://localhost:8484/](http://localhost:8484/)
