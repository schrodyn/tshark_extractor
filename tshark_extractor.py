#!/usr/bin/python
import string;
import binascii;
import sys;
import argparse;
import gzip;
try:
  from cStringIO import StringIO;
except:
  from StringIO import StringIO;
from subprocess import check_output;

def parse_http_stream(matching_item):
  file_bytes=binascii.unhexlify(matching_item[1].replace(":","").strip("\""));
  #find the end of the response header. This should always be \r\n\r\n to satisfy the HTTP standard
  end_of_header=file_bytes.index('\r\n\r\n')+4;
  if 'Content-Encoding: gzip' in matching_item[:end_of_header]:
    #Content-Encoding header indicates gzipped content. try to uncompress
    buf=StringIO(file_bytes[end_of_header:]);
    f = gzip.GzipFile(fileobj=buf);
    file_bytes = f.read();
  else:
    #not gzipped, just grab the response body
    file_bytes = file_bytes[end_of_header:];
  return ["http_stream_"+matching_item[2].strip("\""),file_bytes];

def parse_smb_stream(matching_item):
  file_bytes=binascii.unhexlify(matching_item[4].replace(":","").strip("\""));
  return [matching_item[5].strip("\"") + "_" + matching_item[3].strip("\""), file_bytes];

def parse_tftp_stream(matching_item):
  file_bytes=binascii.unhexlify(matching_item[6].replace('\"','').replace(":",""));
  file_name="";
  if matching_item[7].strip("\"")=='':
    file_name=matching_item[8].strip("\"") + "_" + matching_item[9].strip("\"") + "_" + matching_item[10].strip("\"");
  else:
    file_name=matching_item[7].strip("\"") + "_" + matching_item[9].strip("\"") + "_" + matching_item[10].strip("\"");

  return [file_name,file_bytes];

#extract files matching the specified display filter from the pcap file specified in "infile"
#place them in the "outdir" directory.

def extract_files(outdir, infile, displayfilter):
  #extract all the stream numbers containing the specified display filter
  #return stream numbers and the reassembled data. we'll use the stream number in the file name so it can be found in wireshark later if necessary
  #return columns
  #used to determine protocol
  #[0]:_ws.col.Protocol
  #used by HTTP
  #[1]:tcp.reassembled.data
  #used by HTTP and FTP
  #[2]:tcp.stream
  #used by SMB
  #[3]:smb.fid
  #[4]:smb.file_data
  #[5]:smb.file
  #used by TFTP
  #[6]:data
  #[7]:tftp.source_file
  #[8]:tftp.destination_file
  #[9]:udp.srcport
  #[10]:udp.dstport
  hex_stream_data_list = check_output(["tshark", "-r", infile, "-Y", displayfilter + " && (http || (smb.file_data && smb.remaining==0) || ftp-data || tftp.opcode==3)", "-T", "fields", "-e", "_ws.col.Protocol", "-e", "tcp.reassembled.data", "-e", "tcp.stream", "-e", "smb.fid", "-e", "smb.file_data", "-e", "smb.file","-e", "data", "-e", "tftp.source_file", "-e", "tftp.destination_file", "-e", "udp.srcport", "-e", "udp.dstport", "-E", "quote=d","-E", "occurrence=a", "-E", "separator=^"]).split();

  ftp_data_streams=[];
  reassembled_streams=[];
  #tshark returns stream numbers with no data sometimes. so we'll find the items with hex encoded data and convert them to their normal binary values.
  #when only take the stream info that immediately follows the data to avoid the extraneous items.
  for matching_item in hex_stream_data_list:
    x_item=matching_item.split("^");
    x_protocol=x_item[0].strip("\"");
    if x_protocol=='HTTP':
      parsed_stream = parse_http_stream(x_item);
      search_index=[x for x,y in enumerate(reassembled_streams) if y[1]==parsed_stream[1]];
      if len(search_index)>0:
        parsed_stream[0]=parsed_stream[0]+"_"+search_index;
      reassembled_streams.append(parsed_stream);
    elif x_protocol=='SMB':
      parsed_stream = parse_smb_stream(x_item);
      print(parsed_stream[0]);
      search_index=[x for x,y in enumerate(reassembled_streams) if (y[0])==parsed_stream[0]];
      if len(search_index)>0:
        reassembled_streams[search_index[0]][1]=reassembled_streams[search_index[0]][1]+parsed_stream[1];
      else:
        reassembled_streams.append(parsed_stream);
    elif x_protocol=='TFTP':
      parsed_stream = parse_tftp_stream(x_item);
      search_index=[x for x,y in enumerate(reassembled_streams) if (y[0])==parsed_stream[0]];
      if len(search_index)>0:
        reassembled_streams[search_index[0]][1]=reassembled_streams[search_index[0]][1]+parsed_stream[1];
      else:
        reassembled_streams.append(parsed_stream);
    elif x_protocol=='FTP-DATA':
      ftp_data_streams.append(x_item[2].strip("\""));
    else:
      print("untrapped protocol: ---" + matching_item[0].strip("\"") + "---\n");

  for reassembled_item in reassembled_streams:
    fh=open(outdir + reassembled_item[0],'w');
    fh.write(reassembled_item[1]);
    fh.close();

  for stream_number in ftp_data_streams:
    hex_stream_list = check_output(["tshark", "-q", "-n", "-r", infile, "-z", "follow,tcp,raw," + stream_number]).split("\n");
    list_length = len(hex_stream_list);
    hex_stream_text = ''.join(hex_stream_list[6:list_length-2]);
    file_bytes=binascii.unhexlify(hex_stream_text);
    fh=open(outdir + 'ftp_stream_'+stream_number,'w');
    fh.write(file_bytes);
    fh.close();

def main(args):
  parser = argparse.ArgumentParser();
  parser.add_argument('-o', '--outdir', default='./');
  parser.add_argument('-i', '--infile');
  parser.add_argument('-D', '--displayfilter');
  args = parser.parse_args();

  if not args.infile:
    parser.error('Missing input file argument.');
  
  if not args.displayfilter:
    parser.error('Missing display filter argument.');

  extract_files(vars(args)['outdir'], vars(args)['infile'], vars(args)['displayfilter']);


if __name__ == "__main__":
  main(sys.argv[1:]);
