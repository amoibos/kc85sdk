#!/usr/bin/env python
'''
    Run './kc' for help!
'''
import sys
import os
import json
import subprocess
import struct
import shutil

valid_systems = ['kc85_3', 'kc85_4']

config = {
    'sdcc': 'sdcc', 
    'sdar': 'sdar',
    'mess': 'mess', 
    'z80asm': 'z80asm',
    'makebin': 'makebin',
    'system': 'kc85_3',
}

# generic SDCC flags (lib and exe)
sdcc_flags = [
    '--verbose',
    '-mz80',
    '--std-sdcc99',
    '--fomit-frame-pointer',
    '--disable-warning', '218',
    '--nostdinc',
    '--nostdlib',
    '--no-std-crt0',
    '--opt-code-size',
    '--code-loc', '0x300',
    '--data-loc', '0x200',
]

#-------------------------------------------------------------------------------
def error(msg) :
    print("ERROR: {}".format(msg))
    sys.exit(10)

#-------------------------------------------------------------------------------
def has_config() :
    return os.path.isfile('.config') 

#-------------------------------------------------------------------------------
def load_config() :
    if os.path.isfile('.config') :
        f = open('.config', 'r')
        jsn = json.loads(f.read())
        f.close()
        for key in jsn :
            config[key] = jsn[key]

#-------------------------------------------------------------------------------
def save_config() :
    f = open('.config', 'w')
    f.write(json.dumps(config))
    f.close()

#-------------------------------------------------------------------------------
def check_tool(tool, arg) :
    try :
        subprocess.check_output([tool, arg], stderr=subprocess.STDOUT)
        print("'{}' found".format(tool))
        return True
    except OSError:
        return False

#-------------------------------------------------------------------------------
def do_config() :
    # where is mess?
    # we expect the sdcc and z80asm tools in the path
    mess = os.path.expanduser(raw_input("How to call 'mess': "))
    if not check_tool(mess, '-help') :
        error('{} not found!'.format(mess))
    system = raw_input("Default system ('kc85_3' or 'kc85_4'): ")
    if system not in valid_systems :
        error("must be 'kc85_3' or 'kc85_4'")
    config['mess'] = mess
    config['system'] = system
    if not check_tool(config['makebin'], '-help') :
        error("'makebin not found in path")
    if not check_tool(config['sdcc'], '--help') :
        error("'sdcc' not found in path!") 
    if not check_tool(config['sdar'], '--help') :
        error("'sdar' not found in path!")
    if not check_tool(config['z80asm'], '-help') :
        error("'z80asm' not found in path!")
    save_config()
    print('.config written')

#-------------------------------------------------------------------------------
def set_config(key, val) :
    config[key] = val
    save_config()
    print('.config written')

#-------------------------------------------------------------------------------
def ensure_dirs() :
    for system in valid_systems :
        bin = 'bin/{}'.format(system)
        lib = 'lib/{}'.format(system)
        if not os.path.isdir(bin) :
            os.makedirs(bin)
        if not os.path.isdir(lib) :
            os.makedirs(lib)

#-------------------------------------------------------------------------------
def run_mess(system, name, debug) :
    # run mess with a KCC file
    ensure_dirs()
    mess_path  = config['mess']
    index_html = os.path.dirname(mess_path) + '/web/index.html'
    cmd = [config['mess'], system, 
           '-rompath', 'bios', 
           '-window', '-resolution', '640x512', '-nokeepaspect',
           '-skip_gameinfo',
           '-quik', 'bin/{}/{}.kcc'.format(system, name)]
    if debug :
        cmd.extend(['-debug', '-debugscript', 'bin/{}/__debug.txt'.format(system)])
    subprocess.call(cmd)

#-------------------------------------------------------------------------------
def run_asm(system, src, dst) :
    # assemble a source file with z80asm
    ensure_dirs()
    
    # NOTE: for some reason z80asm is very picky about the --label argument, and
    # putting args into an array seems to mess up the '=', thus put everything into one string
    cmd = '{} --verbose --includepath="lib/asm" --label="bin/{}/{}.lab" -o bin/{}/{}.bin {}'.format(config['z80asm'], system, dst, system, dst, src) 
    return 0 == subprocess.call(cmd, shell=True)

#-------------------------------------------------------------------------------
def run_sdcc_exe(system, src) :    
    ensure_dirs()
    cmd = [config['sdcc'], src, '-DKC85_3=1' if system == 'kc83_3' else '-DKC85_4=1'] 
    cmd.extend(sdcc_flags)
    cmd.extend(['caos.lib', '-L', 'lib/{}'.format(system), '-o', 'bin/{}/'.format(system)])
    print(cmd)
    return 0 == subprocess.call(cmd)

#-------------------------------------------------------------------------------
def run_sdcc_lib(system, sources) :
    ensure_dirs()    
    for src in sources :
        path = 'lib/src/{}.c'.format(src)
        print('>> {}:'.format(path))
        cmd = [config['sdcc'], '-c', path]
        cmd.extend(sdcc_flags)
        cmd.extend(['-o', 'bin/{}/'.format(system)])
        print(cmd)
        if 0 != subprocess.call(cmd) :
            return False
    else :
        return True
    
#-------------------------------------------------------------------------------
def run_sdar(system, files) :
    ensure_dirs()    
    paths = ["bin/{}/{}.rel".format(system, file) for file in files]
    lib = 'lib/{}/caos.lib'.format(system)
    cmd = [config['sdar'], '-rc', lib]
    cmd.extend(paths)
    if 0 == subprocess.call(cmd) :
        print("wrote '{}'".format(lib))
        return True
    else :
        return False

#-------------------------------------------------------------------------------
def run_makebin(system, name) :
    ensure_dirs()    
    src = 'bin/{}/{}.ihx'.format(system, name)
    dst = 'bin/{}/{}.bin'.format(system, name)
    cmd = [config['makebin'], '-p', src, dst]
    return 0 == subprocess.call(cmd)

#-------------------------------------------------------------------------------
def pack_kcc_header(name, start, end) :
    '''
    KCC file format header:
        struct kcc_header
        {
            UINT8   name[10];
            UINT8   reserved[6];
            UINT8   number_addresses;
            UINT8   load_address_l;
            UINT8   load_address_h;
            UINT8   end_address_l;
            UINT8   end_address_h;
            UINT8   execution_address_l;
            UINT8   execution_address_h;
            UINT8   pad[128-2-2-2-1-16];
        };
    '''
    hdr = struct.pack('10s6x7B105x', 
            name.encode("utf-8"), 
            2,    # number_addresses
            start & 0xFF, (start >> 8) & 0xFF,  # load_address_l, load_address_h
            end & 0xFF, (end >> 8) & 0xFF,      # end_address_l, end_address_h
            0, 0) # execution address (not set)
    if len(hdr) != 128 :
        error('ALIGNMENT ERROR')
    return hdr

#-------------------------------------------------------------------------------
def make_test_kcc() :
    # a little KC85/3 program which prints "HELLO WORLD"
    code = ('\x7F\x7FHELLO\x01'
            '\xCD\x03\xF0'
            '\x23'
            'HELLO WORLD\x0D\x0A\x00'
            '\xC9')
    code = code.encode("utf-8")
    start = 0x200
    end = start + len(code)
    #breakpoint()
    kcc = pack_kcc_header('HELLO', start, end) + code
    return kcc

#-------------------------------------------------------------------------------
def do_test(system) :
    ensure_dirs()
    kcc = make_test_kcc()
    with open('bin/{}/test.kcc'.format(system), 'wb') as f :
        f.write(kcc)
    run_mess(system, 'test', False)

#-------------------------------------------------------------------------------
def do_make(system, src) :
    dst, ext = os.path.splitext(src)
    _, dst = os.path.split(dst)

    # run compiler...
    if not run_sdcc_exe(system, src) :
        error("Failed compiling '{}'!".format(src))
    # generate binary file from Intel hex file
    if not run_makebin(system, dst) :
        error("Failed makebin of '{}'!".format(src))
    # package binary into a KCC file
    with open('bin/{}/{}.bin'.format(system, dst), 'rb') as binfile :
        # strip the first 0x200 bytes (data section starts
        # at 0x200, code section at 0x300)
        bin = binfile.read()[0x200:]
        start = 0x200
        end = start + len(bin)
        kcc = pack_kcc_header(dst.upper(), start, end) + bin
        with open('bin/{}/{}.kcc'.format(system, dst), 'wb') as kccfile :
            kccfile.write(kcc)
        print('wrote bin/{}/{}.kcc'.format(system, dst))

#-------------------------------------------------------------------------------
def do_asm(system, src, dst) :
    # compile to bin/dst.bin
    _, dst = os.path.split(dst)
    if run_asm(system, src, dst) :
        # load assembled binary and package into KCC
        with open('bin/{}/{}.bin'.format(system, dst), 'rb') as binfile :
            bin = binfile.read()
            start = 0x200
            end = start + len(bin)
            kcc = pack_kcc_header(dst.upper(), start, end) + bin
            with open('bin/{}/{}.kcc'.format(system, dst), 'wb') as kccfile :
                kccfile.write(kcc)
            print('wrote bin/{}/{}.kcc'.format(system, dst))
    else :
        error('Failed to assemble {}'.format(src))

#-------------------------------------------------------------------------------
def do_run(system, name) :
    # run a compiled/assembled KCC file through mess
    run_mess(system, name, False)

#-------------------------------------------------------------------------------
def symbol_addr(system, name, brk) :
    '''
    Try to resolve a symbol/label into a breakpoint address, either
    from a .map file (generated by C compiler) or .lab file 
    (generated by assembler)
    '''
    map_addr = None
    map_path = 'bin/{}/{}.map'.format(system, name)
    lab_addr = None
    lab_path = 'bin/{}/{}.lab'.format(system, name)

    # try read symbol from .map file
    if os.path.isfile(map_path) :
        with open(map_path, 'r') as f :
            symbol = '_{} '.format(brk)
            print("Looking for '{}' in '{}'...".format(symbol, map_path))
            lines = f.readlines()
            for line in lines :
                if symbol in line :
                    map_addr = line.split()[0]
                    print("Found '{}' in '{}' at {}".format(symbol, map_path, map_addr))
                    break
            else :
                print("...not found.")
    
    # try read symbol from .lab file
    # format is:
    # label:    equ addr
    if os.path.isfile(lab_path) :
        with open(lab_path, 'r') as f :
            label = '{}:'.format(brk)
            print("Looking for '{}' in '{}'...".format(label, lab_path))
            lines = f.readlines()
            for line in lines :
                if label in line :
                    # address is 3rd element in line, need to strip leading $
                    lab_addr = line.split()[2][1:]
                    print("Found '{}' in '{}' at {}".format(label, lab_path, lab_addr))
                    break

    addr = map_addr if lab_addr is None else lab_addr
    return addr

#-------------------------------------------------------------------------------
def do_debug(system, name, brk) :

    print('do_debug {} {} {}'.format(system, name, brk))
    addr = symbol_addr(system, name, brk)
    with open('bin/{}/__debug.txt'.format(system), 'w') as f :
        if addr :
            print('Setting breakpoint at ${}'.format(addr))
            f.write('go {}'.format(addr))
        else :
            print('No breakpoint set')
            f.write(' ')

    # call MESS with debugger active
    run_mess(system, name, True)

#-------------------------------------------------------------------------------
def do_libs() :
    # rebuild the caos.lib
    for system in valid_systems :
        files = [
            'caos_color', 
            'caos_clear',
            'caos_clear_color_buf',
            'caos_wait',
            'caos_irm',
            'caos_line'
        ]
        if not run_sdcc_lib(system, files) :
            error('Compiling lib failed!')
        if not run_sdar(system, files) :
            error('Building lib failed!')

#===============================================================================
load_config()
if len(sys.argv) == 1 or len(sys.argv) == 2 and sys.argv[1] == '-help' or sys.argv[1] == '--help' :
    print('\nC/ASM SDK for KC85/3 and KC85/4 home computers.\n')
    print('kc (cmd) [args...]\n')
    print('kc config')
    print('  run once to configure for your local environment')
    print('kc system (kc85_3 or kc85_4)')
    print('  select default system')
    print('kc make c-source')
    print('  compile c source into program')
    print('kc clean')
    print('  clean build files')
    print('kc asm (asm-source) [prog]')
    print('  assemble asm source into program')
    print('kc run (prog)')
    print('  run a compiled program in MESS')
    print('kc debug (prog) [break-func | break-label]')
    print('  like run, but with debugger activated, optionally break at C func or ASM label')
    print('kc test')
    print("  test run with a hardcoded 'HELLO WORLD' program")
    print('kc libs')
    print('  rebuild caos.lib for kc85_3 and kc85_4\n\n')

else :
    cmd = sys.argv[1]
    if cmd == 'config' :
        do_config()
    elif cmd == 'system' :
        if len(sys.argv) >= 3 and sys.argv[2] in valid_systems:
            set_config('system', sys.argv[2])
        else :
            error('system name expected (kc85_3 or kc85_4)')
    elif cmd == 'make' :
        if len(sys.argv) >= 3 :
            src = sys.argv[2]
            do_make(config['system'], src)
        else :
            error('excpected source file name')
    elif cmd == 'clean' :
        for system in valid_systems :
            path = 'bin/{}'.format(system)
            if os.path.isdir(path) :
                shutil.rmtree(path)
        print('done.')
    elif cmd == 'asm' :
        src = 'out.s'
        dst = 'out'
        if len(sys.argv) >= 3 :
            src = sys.argv[2]
            dst, ext = os.path.splitext(src)
        if len(sys.argv) >= 4:
            dst = sys.argv[3]
        do_asm(config['system'], src, dst)
    elif cmd == 'run' :
        prg = 'out'
        if len(sys.argv) >= 3 :
            prg = sys.argv[2]
        do_run(config['system'], prg)
    elif cmd == 'debug' :
        prg = 'out'
        brk = None
        if len(sys.argv) >= 3 :
            prg = sys.argv[2]
        if len(sys.argv) >= 4 :
            brk = sys.argv[3]
        do_debug(config['system'], prg, brk)
    elif cmd == 'test' :
        do_test(config['system'])
    elif cmd == 'lib' :
        do_libs()
    else :
        error('Unknown cmd: {}'.format(cmd))
