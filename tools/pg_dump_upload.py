#!/usr/bin/python3

import sys
import time
import socket
import os
import argparse
import gnupg

parser = argparse.ArgumentParser (description="This program takes a database dump, encrypts and uploads it to S3")

args_general = parser.add_argument_group(title="General options")
args_general.add_argument('-n', '--hostname', default=socket.gethostname(), help='name of the machine')
args_general.add_argument('-c', '--config_file', default='/home/postgres/etc/pg_dump.conf', help='file containing contents to dump')
args_general.add_argument('-ac', '--all_config_file', default='/home/postgres/etc/pg_dumpall.conf', help='file containing name of database used by pg_dumpall and move_all')
args_general.add_argument('-l', '--lock_file', default='/var/tmp/postgres_dump.lock', help='this file ensures only one backup job runs at a time')

args_postgres = parser.add_argument_group(title="Postgres options")
args_postgres.add_argument('-dp', '--pg_dump_path', help='path to pg_dump command')
args_postgres.add_argument('-da', '--pg_dumpall_path',help='path to pg_dumpall command')
args_postgres.add_argument('-pp', '--postgres_port', help='port on which the postgres instance is running')
args_postgres.add_argument('-df', '--dump_file_path', help='The output file to store the pg dump')

args_gpg = parser.add_argument_group(title='GPG options')
args_gpg.add_argument('-gp', '--gpg_path', help='path to gpg binary')
args_gpg.add_argument('-r', '--recipient', help='recipient\'s key name or email')
args_gpg.add_argument('-gd', '--gnupg_dir_path', help='path to .gnupg directory')

args_s3 = parser.add_argument_group(title='S3 options')
args_s3.add_argument('-sp', '--s3_path',  help='path to s3cmd executable')
args_s3.add_argument('-sf', '--s3_upload_files', help='comma separated list of database backups to upload to S3')
args_s3.add_argument('-sr', '--s3_upload_role_files', help='comma separated list of database - role backups to upload to S3')
args_s3.add_argument('-sl', '--s3_bucket_link', help='S3 bucket link on AWS')

args = parser.parse_args()

# Timestamp for backed up filenames
start_time = time.strftime("%Y-%m-%d_%H:%M:%S")

# Path normalizations and joins
config_file = os.path.normpath(args.config_file)
all_config_file = os.path.normpath(args.all_config_file)
lock_file = os.path.normpath(args.lock_file)
pg_dump_path = os.path.normpath(args.pg_dump_path)
pg_dumpall_path = os.path.normpath(args.pg_dumpall_path)
dump_file_path = os.path.join(os.path.normcase(args.dump_file_path), '')
gpg_path = os.path.normpath(args.gpg_path)
gnupg_dir_path = os.path.normpath(args.gnupg_dir_path)
s3_path = os.path.join(os.path.normpath(args.s3_path), "s3cmd")
s3_bucket_link = os.path.join(args.s3_bucket_link, '')

def check_lock():
    if os.path.isfile(lock_file):
        sys.exit('ERROR: lock file already exists: %s' % lock_file)
    else:
        open(lock_file, 'w+').close()
        print('Lock file created.')


def take_dump():
    try:
        with open(config_file, 'r') as f:
            for db in f:
                if db.strip():
                    db = db.replace("\n", "")
                    dump_command = pg_dump_path + " -p 5432 -U postgres -v -Fc -f " + dump_file_path + db.split()[-1] + "_" + start_time  + ".sql" + " " + db + " 2>> " + dump_file_path + db.split()[-1] + "_" + start_time  + ".log"
                    os.system(dump_command)
                    print('backup of ' + db.split()[-1] + ' completed successfully')
                    print('dump command : ' + dump_command)

    except:
        print('ERROR: bash command did not execute properly')


def take_dumpall():
    try:
       with open(all_config_file, 'r') as x:
           db = x.read()
           db_name = db.replace('\n','')
           print("Taking globals dump")
           dumpall_command = pg_dumpall_path + " -p5432 -g " + " 1>> " + dump_file_path + db_name + "_" + start_time  + "_" + "roles.sql"
           os.system(dumpall_command)
           print('backup of globals completed successfully')
           print("Encrypting global file")
           gpg = gnupg.GPG(gpgbinary=gpg_path, gnupghome=gnupg_dir_path)
           plain_text_role = open(dump_file_path + db_name + "_" + start_time + "_roles.sql", 'rb')
           encrypted_role = dump_file_path + db_name + "_" + start_time + "_roles.sql.gpg"
           gpg.encrypt_file(plain_text_role, args.recipient, output=encrypted_role)
           print('backup of globals  encrypted successfully')
           print('uploading globals to s3')
           s3_command = s3_path + " put FILE " + dump_file_path + db_name + '_' + start_time + "_roles.sql.gpg " + s3_bucket_link
           os.system(s3_command)
           print('backup of globals uploaded successfully')

    except:
        print('ERROR: dumpall command did not execute properly')


def gpg_encrypt():
    try:
        upload_files = args.s3_upload_files.split(',')
        gpg = gnupg.GPG(gpgbinary=gpg_path, gnupghome=gnupg_dir_path)

        try:
            for file in upload_files:
                plain_text_file = open(dump_file_path + file.strip() + "_" + start_time + ".sql", 'rb')
                encrypted_file = dump_file_path + file.strip() + "_" + start_time + ".sql.gpg"
                gpg.encrypt_file(plain_text_file, args.recipient, output=encrypted_file)
                print('backup of ' + file.strip() + ' encrypted successfully')
        except:
            print('ERROR: Could not encrypt file')

    except:
        print('ERROR: Could not find gpg executable and/or gnupg directory')


def s3_upload():
    upload_files = args.s3_upload_files.split(',')

    try:
        for file in upload_files:
            s3_command = s3_path + " put " + dump_file_path + file.strip() + "_" +  start_time + ".sql.gpg " + s3_bucket_link
            os.system(s3_command)
            print('backup of ' + file.strip() + ' uploaded successfully...')

    except:
        print('ERROR: s3cmd did not execute successfully')

    list_contents = s3_path + " ls " + s3_bucket_link
    os.system(list_contents)



def move_files():
    try:
        with open(config_file, 'r') as f:
            for db in f:
                if db.strip():
                    db = db.replace('\n','')
                    db_name = db.split()[-1]
                    db_file_name = db_name + "_" + start_time + ".sql"
                    log_file_name = db_name + "_" + start_time + ".log"
                    if not os.path.exists(os.path.join(dump_file_path, db_name)):
                        os.makedirs(os.path.join(dump_file_path, db_name))
                    if os.path.isfile(os.path.join(dump_file_path, db_file_name)):
                        source = os.path.join(dump_file_path, db_file_name)
                        target = os.path.join(dump_file_path, db_name, db_file_name)
                        print ("source: " + source + "\n target: " + target)
                        os.rename(source, target)
                    if os.path.isfile(os.path.join(dump_file_path, log_file_name)):
                        source = os.path.join(dump_file_path, log_file_name)
                        target = os.path.join(dump_file_path, db_name, log_file_name)
                        print ("source: " + source + "\n target: " + target)
                        os.rename(source, target)

    except:
        print("ERROR: Could not move files to specified location")

def move_dumpall_files():
    try:
       with open(all_config_file, 'r') as x:
           db = x.read()
           db_name = db.replace('\n','')
           global_file =  db_name + "_" + start_time + "_roles.sql"
           if not os.path.exists(os.path.join(dump_file_path, db_name)):
              os.makedirs(os.path.join(dump_file_path, db_name))
           if os.path.isfile(os.path.join(dump_file_path, global_file)):
              source = os.path.join(dump_file_path, global_file)
              print (source) 
              target = os.path.join(dump_file_path, db_name, global_file)
              print ("source: " + source + "\n target: " + target)
              os.rename(source, target)

    except:
        print("ERROR: Could not move dumpall file to specified location")


def cleanup():
    if os.path.exists(lock_file):
        os.remove(lock_file)

    filelist = [ f for f in os.listdir(dump_file_path) if f.endswith(".sql.gpg") ]
    for f in filelist:
        os.remove(os.path.join(dump_file_path, f))

    print('All cleaned up.')


check_lock()
take_dump()
take_dumpall()
gpg_encrypt()
s3_upload()
move_files()
move_dumpall_files()
cleanup()
