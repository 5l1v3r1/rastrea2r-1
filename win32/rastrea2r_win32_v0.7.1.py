#!/usr/bin/env python
#
# rastrea2r win32 client
#
# by Ismael Valenzuela @aboutsecurity / Foundstone Services (Intel Security)


import os
import sys
import yara
import psutil  # New multiplatform library
import subprocess
import hashlib
import zipfile

from time import gmtime, strftime
from requests import post
from argparse import ArgumentParser
from mimetypes import MimeTypes


__author__ = 'ismael.valenzuela@intel.com'
__version__ = '0.7.1'

# see HISTORY.rst for details

""" Variables """

server_port = 8080 # Default REST server port
BLOCKSIZE = 65536
mime=MimeTypes()


def hashfile(file):

    """ Hashes output files with SHA256 using buffers to reduce memory impact """

    hasher = hashlib.sha256()

    with open(file, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        hasher.update(buf)

    return(hasher.hexdigest())


def fetchyararule(server, rule):

    """ Fetches yara rule from REST server"""

    try:
        rule_payload = {'rulename':rule}
        r = post('http://'+server+':'+str(server_port)+'/getrule', data=rule_payload)
    except:
        sys.exit("\nFailed to contact the server")

    if r.text == "":
        sys.exit("\nError: The file requested doesn't exist\n")
    else:
        return r.text


def yaradisk(path, server, rule, silent):

    """ Yara file/directory object scan module """

    rule_text=fetchyararule(server,rule)

    if not silent:
        print '\nPulling ' +rule+ ' from ' +server+ '\n'
        print rule_text + '\n'

        print '\nScanning ' +path+ '\n'

    rule_bin=yara.compile(sources={'namespace':rule_text})

    for root, dirs, filenames in os.walk(path):
        for name in filenames:
            try:
                file_path=os.path.join(root,name)

                mime_type = mime.guess_type(file_path)
                if "openxmlformats-officedocument" in mime_type[0]: # If an OpenXML Office document (docx/xlsx/pptx,etc.)
                    doc = zipfile.ZipFile(file_path) # Unzip and scan in memory only
                    for doclist in doc.namelist():
                        matches=rule_bin.match(data=doc.read(doclist))
                        if matches: break
                else:
                    matches=rule_bin.match(filepath=file_path)

                if matches:
                    payload={"rulename":matches[0],
                             "filename":file_path,
                             "module":'yaradisk',
                             "hostname":os.environ['COMPUTERNAME']}
                    if not silent:
                        print payload

                    p=post('http://'+server+':'+str(server_port)+'/putfile',data=payload)
            except:
                continue


def yaramem(server, rule, silent):

    """ Yara process memory scan module """

    rule_text=fetchyararule(server,rule)

    if not silent:
        print '\nPulling ' +rule+ ' from ' +server+ '\n'
        print rule_text + '\n'

        print '\nScanning running processes in memory\n'

    mypid=os.getpid()

    rule_bin=yara.compile(source=rule_text)

    for process in psutil.process_iter():
        try:
            pinfo = process.as_dict(attrs=['pid','name','exe','cmdline'])
        except psutil.NoSuchProcess:
            pass
        else:
            if not silent:
                print(pinfo)

        client_pid=pinfo['pid']
        client_pname=pinfo['name']
        client_ppath=pinfo['exe']
        client_pcmd=pinfo['cmdline']

        if client_pid!=mypid:
            try:
                matches=rule_bin.match(pid=client_pid)
            except:
                if not silent:
                    print ('Failed scanning process ID: %d' %client_pid)
                continue

            if matches:
                payload={"rulename":matches,
                             "processpath":client_ppath,
                             "processpid":client_pid,
                             "module":'yaramem',
                             "hostname":os.environ['COMPUTERNAME']}
                if not silent:
                    print payload

                p=post('http://'+server+':'+str(server_port)+'/putpid',data=payload)


def memdump(tool_server, output_server, silent):

    """ Memory acquisition module """

    smb_bin=tool_server + r'\tools' # TOOLS Read-only share with third-party binary tools

    smb_data=output_server + r'\data' + r'\memdump-' + os.environ['COMPUTERNAME'] # DATA Write-only share for output data
    if not os.path.exists(r'\\'+smb_data):
        os.makedirs(r'\\'+smb_data)

    if not silent:
        print '\nSaving output to '+r'\\'+smb_data

    tool=('winpmem -') # Sends output to STDOUT

    fullcommand=tool.split()
    commandname=fullcommand[0].split('.')

    recivedt=strftime('%Y%m%d%H%M%S', gmtime()) # Timestamp in GMT

    f=open(r'\\'+smb_data+r'\\'+recivedt+'-'+os.environ['COMPUTERNAME']+'-'+commandname[0]+'.img','w')

    if not silent:
        print '\nDumping memory to ' +r'\\'+smb_data+r'\\'+recivedt+'-'+os.environ['COMPUTERNAME']+'-'\
              +commandname[0]+'.img\n'

    pst = subprocess.call(r'\\'+smb_bin+r'\\'+tool, stdout=f)

    with open(r'\\' + smb_data + r'\\' + recivedt + '-' + os.environ['COMPUTERNAME'] + '-' + 'sha256-hashing.log', 'a') as g:
        g.write("%s - %s \n\n" % (f.name, hashfile(f.name)))


def triage(tool_server, output_server, silent):

    """ Triage collection module """

    createt=strftime('%Y%m%d%H%M%S', gmtime()) # Timestamp in GMT
    smb_bin=tool_server + r'\tools' # TOOLS Read-only share with third-party binary tools

    smb_data=output_server + r'\data' + r'\triage-' + os.environ['COMPUTERNAME'] + r'\\' + createt # DATA Write-only share for output data
    if not os.path.exists(r'\\'+smb_data):
        os.makedirs(r'\\'+smb_data)

    if not silent:
        print '\nSaving output to '+r'\\'+smb_data

    """ Add your list of Sysinternal / third-party / BATCH files here """

    tool=(
         'systeminfo.cmd', # Gathers systeminfo
         'set.cmd', # Gathers Set variables
         'dir-tree.cmd', # Enumerates C:\ directory tree
         'ipconfig.cmd', # Gathers IP information
         'ip-routes.cmd', # Gathers IP routing information
         'arp.cmd', # Gathers ARP table information
         'dns.cmd', # Gathers DNS Cache information
         'users.cmd', # Gathers User/local Admin accounts
         'shares.cmd', # Gathers local shares information
         'firewall.cmd', # Gathers local firewall information
         'hosts.cmd', # Captures Host file information
         'sessions.cmd', # Gathers Active Session information
         'nbtstat.cmd', # Gathers NetBios Sessions information
         'netstat.cmd', # Gathers Netstat with process IDs
         'services.cmd', # Gathers services information
         'process-list.cmd', # Gathers WMIC Proccess list full
         'tasklist.cmd', # Gathers Tasklist /m information
         'at-schtasks.cmd', # Gathers scheduled tasks information
         'startup-list.cmd', # Gathers WMIC Startup list full
         'zRemote.bat',
         'psinfo.exe /accepteula', # Gathers basic system information
         'diskext.exe /accepteula', # Gathers disks mounted
         'logonsessions.exe /p /accepteula', # Gathers logon sessions and process running in them
         'psfile.exe /accepteula', # Gathers if any files are opened remotely
         'psloggedon.exe -p /accepteula', # Gathers all logon sessions with running processes
         'psloglist.exe -d 1 /accepteula', # Gathers all events since in the last day
         'pslist.exe -t /accepteula', # Gather system process tree
         'psservice.exe /accepteula', # Gathers all the services information
         'tcpvcon.exe -a /accepteula', # Gathers TCP/UDP connections
         'handle.exe -a -u /accepteula', # Gathers what files are open by what processes and more
         'listdlls.exe -r -u -v /accepteula', # Gathers all DLLs not loaded in base address, unsigned and shows version information') #Runs local commands via a batch file in the tools directory.
         'autorunsc.exe -a * -ct -h /accepteula', # Gathers all the autoruns service points

    )
    """ BATCH files must be called with the .bat extension """

    with open(r'\\'+smb_data+r'\\'+createt+'-'+os.environ['COMPUTERNAME']+'-'+'sha256-hashing.log','a') as g:
        for task in tool: # Iterates over the list of commands

            fullcommand=task.split()
            commandname=fullcommand[0].split('.')

            if not silent:
                print '\nSaving output of ' +task+ ' to '+r'\\'+smb_data+r'\\'+createt+'-'+os.environ['COMPUTERNAME']\
                    +'-'+commandname[0]+'.log\n'
		
            f=open(r'\\'+smb_data+r'\\'+createt+'-'+os.environ['COMPUTERNAME']+'-'+commandname[0]+'.log','w')

            pst = subprocess.call(r'\\'+smb_bin+r'\\'+task, stdout=f)

            g.write("%s - %s \n\n" % (f.name, hashfile(f.name)))


def main():

    parser = ArgumentParser(description='::Rastrea2r RESTful remote Yara/Triage tool for Incident Responders '
                                        'by Ismael Valenzuela @aboutsecurity / Foundstone (Intel Security)::')

    subparsers = parser.add_subparsers(dest="mode", help='modes of operation')

    """ Yara filedir mode """

    list_parser = subparsers.add_parser('yara-disk', help='Yara scan for file/directory objects on disk')
    list_parser.add_argument('path', action='store', help='File or directory path to scan')
    list_parser.add_argument('server', action='store', help='rastrea2r REST server')
    list_parser.add_argument('rule', action='store', help='Yara rule on REST server')
    list_parser.add_argument('-s', '--silent', action='store_true', help='Suppresses standard output')


    """Yara memory mode"""

    list_parser = subparsers.add_parser('yara-mem', help='Yara scan for running processes in memory')
    list_parser.add_argument('server', action='store', help='rastrea2r REST server')
    list_parser.add_argument('rule', action='store', help='Yara rule on REST server')
    list_parser.add_argument('-s', '--silent', action='store_true', help='Suppresses standard output')

    """Memory acquisition mode"""

    list_parser = subparsers.add_parser('memdump', help='Acquires a memory dump from the endpoint')
    list_parser.add_argument('TOOLS_server', action='store', help='Binary tool server (SMB share)')
    list_parser.add_argument('DATA_server', action='store', help='Data output server (SMB share)')
    list_parser.add_argument('-s', '--silent', action='store_true', help='Suppresses standard output')

    """Triage mode"""

    list_parser = subparsers.add_parser('triage', help='Collects triage information from the endpoint')
    list_parser.add_argument('TOOLS_server', action='store', help='Binary tool server (SMB share)')
    list_parser.add_argument('DATA_server', action='store', help='Data output server (SMB share)')
    list_parser.add_argument('-s', '--silent', action='store_true', help='Suppresses standard output')

    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)
    args=parser.parse_args()

    if args.mode == 'yara-disk':
            yaradisk(args.path,args.server,args.rule,args.silent)

    elif args.mode == 'yara-mem':
            yaramem(args.server,args.rule,args.silent)

    elif args.mode == 'memdump':
            memdump(args.TOOLS_server,args.DATA_server,args.silent)

    elif args.mode == 'triage':
            triage(args.TOOLS_server,args.DATA_server,args.silent)


if __name__ == '__main__':
    main()