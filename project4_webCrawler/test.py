#!/usr/bin/python

# USED FOR PYCHARM

import socket
import sys
import zlib
from HTMLParser import HTMLParser
from urlparse import urlparse

# username and password from input
USERNAME = ''
PASSWORD = ''

# all the various paths we can get from parsing
fakebook_url = urlparse('http://fring.ccs.neu.edu/fakebook/')
login_url = urlparse('http://fring.ccs.neu.edu/accounts/login/?next=/fakebook/')
full_login_path = "/accounts/login/?next=/fakebook/"
HOST = fakebook_url.netloc
# fakebook_url.netloc fring.ccs.neu.edu
FAKEBOOK_PATH = fakebook_url.path
LOGIN_PATH = login_url.path
HTTP_VERSION = "HTTP/1.1"

# the port of the server
PORT = 80
HOST_PORT = (HOST, PORT)

# all the paths that are already visited
paths_visited = set()
# all the paths that needed to be visited
paths_tovisit = set()
# all the secret flags gathered
secret_flags = set()
# indicates whether the program is logged in to fakebook
logged_in = False
# the secret csrf token and session_id crawled from the initial page
csrf = ''
session_id = ''
# the initial socket that sends and receives HTTP requests and responses
sock = None



class PageParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)

    """
    handle the start tags of the webpage
    @param tag - the start tag
    @param attrs - the outstanding attribute
    """
    def handle_starttag(self, tag, attrs):
        global paths_visited, paths_tovisit, secret_flags
        # find links in the page
        if tag == 'a':
            for attr, val in attrs:
                if attr == 'href':
                    val_path = urlparse(val).path
                    # only add to tovisit list if the url has not been visited
                    # doesn't exist in tovisit list already, and it's valid
                    if val_path not in paths_visited and val.startswith('/fakebook'):
                        paths_tovisit.add(val_path)

    """
        handle the data of the webpage
        @param data - the data contained inside the tags
    """
    def handle_data(self, data):
        global paths_visited, paths_tovisit, secret_flags, csrf, session_id, logged_in
        # don't bother checking for keywords if we're logged in
        if not logged_in and "csrftoken" in data:
            # grab token if not logged in
            csrf = data.split("csrftoken=")[1].split(";")[0]
        # grab session id if not logged in
        if not logged_in and "sessionid" in data:
            session_id = data.split("sessionid=")[1].split(";")[0]
        if "FLAG:" in data:
            # parse for the flag and add to list
            flag = data.split(" ")[1]
            secret_flags.add(flag)
            print(flag)

"""
receive HTTP responses using the socket
@param sock - the socket used to receive response
@return full_message - the full response received from the socket
"""
def recv_response():
    global sock, HOST_PORT
    full_message = ''
    try:
        full_message = sock.recv(1000000)
    except socket.error as e:
        # Connection reset by peer, reopen socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(HOST_PORT)
        recv_response()
    return full_message


"""
login to fakebook with the token and session id
@param path - the given login path
@return response - the HTTP GET response

"""
def login_GET(path):
    global HTTP_VERSION, HOST, HOST_PORT, sock

    # constructs the initial GET request
    request = '''\
GET %s %s
Host: %s
Accept-Encoding: gzip

'''  % (path, HTTP_VERSION, HOST)
    try:
        #create a new socket and send the HTTP request
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # connect to the host and the port
        sock.connect(HOST_PORT)
        # send the request to the socket
        sock.sendall(request)
        # receive from the socket
        response = recv_response()
        decompressed_response = decompress_response(response)
        return decompressed_response
    except socket.error as e:
        # failed to create socket
        print('ERROR: failed to create socket at initial get! %s' % e)
        exit(1)

"""
HTTP GET with cookie, after logged in
@param path - the given path of the webpage
@return response - the HTTP response of the request
"""
def cookie_GET(path):
    global HTTP_VERSION, HOST, csrf, session_id, HOST_PORT, sock

    # including the sessionid in request so we can access the logged in info
    request = '''\
GET %s %s
Host: %s
Accept-Encoding: gzip
Cookie: csrftoken=%s; sessionid=%s

''' % (path, HTTP_VERSION, HOST, csrf, session_id)

    try:
        # create a new socket and send the HTTP request with the cookie
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(HOST_PORT)
        sock.sendall(request)
        response = recv_response()
        decompressed_response = decompress_response(response)
        return decompressed_response
    except socket.error as e:
        # failed to create socket
        print("ERROR: failed to create socket in GET with a cookie! %s" % e)
        exit(1)


"""
login to fakebook using HTTP POST
@param path - the given login path
@return response - the HTTP POST response
"""
def login_POST(path):
    global HTTP_VERSION, HOST, csrf, session_id, USERNAME, PASSWORD, HOST_PORT, sock

    # constructs the message body of the HTTP POST request
    data = "username=%s&password=%s&csrfmiddlewaretoken=%s&next=%%2Ffakebook%%2F" % (USERNAME, PASSWORD, csrf)

    #the information we're using to login
    # content-length is necessary for framing
    request = '''\
POST %s %s
Host: %s
Accept-Encoding: gzip
Content-Length: %d
Cookie: csrftoken=%s; sessionid=%s

%s
''' % (path, HTTP_VERSION, HOST, len(data), csrf, session_id, data)

    try:
        # send the post request
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # connect to the host and the port
        sock.connect(HOST_PORT)
        # send the request to the server
        sock.sendall(request)
        # receive response from the server
        response = recv_response()
        decompressed_response = decompress_response(response)
        return decompressed_response
    except socket.error as e:
        # failed to create socket
        print("ERROR: failed to create socket when POST! %s" % e)
        exit(1)


"""
initial login function that:
GET the first fakebook page
Retrieve the token and the session id from the GET response
POST to login with the token and the session id
update cookie
@param path - the given login path
"""
def login(path):
    global HOST_PORT, LOGIN_PATH, logged_in, sock

    # GET the initial fakebook login page
    get_response = login_GET(path)
    # handle the response of the first GET
    get_status_code = handle_http_status_codes(get_response, full_login_path)
    # if the status_code is 200, then crawl
    if get_status_code == '200':
        crawl_webpage(get_response)
    # if the status_code is redirect, then GET using the new path
    elif get_status_code == '302':
        # retry using the redirected path
        login(paths_tovisit.pop())
    # if the status_code is 500, then retry login using the same path
    elif get_status_code == '500':
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(HOST_PORT)
        # retry using the same path
        login(path)
    else:
        # if status_code is 404, etc, then abondon the path and exit the program
        print("First GET failed, cannot find the given path, exit the program")
        exit(1)

    # POST with the session id and token
    post_response = login_POST(LOGIN_PATH)
    # renew token
    crawl_webpage(post_response)
    # handle the response status code
    post_status_code = handle_http_status_codes(post_response, LOGIN_PATH)
    # if status_code is 200
    if post_status_code == '200':
        # if did not successfully log in, then username and password is wrong
        if '<a href="/accounts/login/">Log in</a>' in post_response:
            print("Given Username and Password incorrect! Please retry")
            exit(1)
    # login is successful
    logged_in = True


"""
decompresses the HTTP response message body
@response - the HTTP response received (before decompress)
@return the decompressed response
"""
def decompress_response(response):
    try:
        # split the message header from the compressed section
        message = response.split("\r\n\r\n")
        compressed = message[1]
        # decompress the encoded message
        response = zlib.decompress(compressed, zlib.MAX_WBITS|32)
        # put the response back together so it can be parsed properly
        response = message[0] + response
    except:
        # don't modify response, just send it as we got it
        pass
    return response


"""
crawl the webpage to find token, session_id, and flag
@param response - the given HTTP response to crawl
"""
def crawl_webpage(response):
    global csrf, session_id

    # initialize the page parser
    parser = PageParser()
    #check for links and other tags
    parser.feed(response)


"""
handle the http status code
    200 - accepted
    301 - moved permanently. try the request again using the new URL given by the server in the Location header.
    403 - Forbidden
    404 - Not Found
        Server may return these codes in order to trip up your crawler.
        Crawler should abandon the URL that generated the error code.
    500 - Internal Server Error
        Server may randomly return this error code to your crawler.
        Crawler should re-try the request for the URL until the request is successful.
@param response - the given HTTP response to crawl
@param path - the given path of the received response
@return status_code - the status code of the HTTP response
"""
def handle_http_status_codes(response, path):
    try:
        # parse for status_code
        status_code = response.split(' ')[1]
    except:
        # status_code couldn't be parsed, retry
        status_code = '500'
    # Valid Response
    if status_code == '200':
        pass
    # Redirect
    if status_code == '301' or status_code == '302':
        # parse the new location
        new_path = str(urlparse(response.split('Location: ')[1].split('\n')[0]).path).rstrip('\r')
        # add the new_path to the list of tovisit path if it was not visited
        if new_path not in paths_visited:
            paths_tovisit.add(new_path)
        # add the previous path to the list of already visited list
        paths_visited.add(path)
        # remove the previous path if it is in tovisit list
        if path in paths_tovisit:
            paths_tovisit.remove(path)
    # Not Found
    if status_code == '403' or status_code == '404':
        # failed to get page, add to global variables so we don't visit here again
        if path in paths_tovisit:
            paths_tovisit.remove(path)
        paths_visited.add(path)
    # Internal Server Error
    if status_code == '500':
        #retry with the same path and (hopefully) a different response
        response = cookie_GET(path)
        # handle the response
        handle_http_status_codes(response, path)
    return status_code


"""
the main program
"""
def main():
    global USERNAME, PASSWORD, full_login_path

    # if given incorrect input argument, then quit
    if len(sys.argv) < 3:
        print("Please input Username and Password for logging into fakebook!")
        exit(1)
    # takes input username and password
    USERNAME = sys.argv[1]
    PASSWORD = sys.argv[2]
    # login into fakebook
    login(full_login_path)
    # if we haven't found all 5 flags yet
    while len(secret_flags) < 5:
        # iterate over pathList so we don't modify it while going over
        path_list = list(paths_tovisit)
        for path in path_list:
            # found all the flags, gracefully quit
            if len(secret_flags) >= 5:
                break
            # GET webpage using the given path with login cookie
            response = cookie_GET(path)
            # handle the status code of the response
            status_code = handle_http_status_codes(response, path)
            if status_code == '200':
                # crawl the webpage and parse it for more links
                crawl_webpage(response)
                paths_visited.add(path)
                paths_tovisit.remove(path)
    sock.close()
    # mission completed, gracefully exit the program
    sys.exit(0)


if __name__ == "__main__":
    main()




