import subprocess

class BreakOnLoadSharedLibrary(gdb.Breakpoint):
    def __init__(self, module_name):
        super(BreakOnLoadSharedLibrary, self).__init__("dlopen", type=gdb.BP_BREAKPOINT, internal=False)
        self.module_name = module_name
        self.silent = True
        self.enabled = True
        return

    def stop(self):
        reg = current_arch.function_parameters[0]
        addr = lookup_address(get_register(reg))
        if addr.value==0:
            return False
        path = read_cstring_from_memory(addr.value, max_length=None)
        if path.endswith(self.module_name):
            return True
        return False


class WindbgSxeCommand(GenericCommand):
    """WinDBG compatibility layer: sxe (set-exception-enable): break on loading libraries."""
    _cmdline_ = "sxe"
    _syntax_  = "{:s} [ld,ud]:module".format(_cmdline_)
    _example_ = "{:s} ld:mylib.so".format(_cmdline_)

    def __init__(self):
        super(WindbgSxeCommand, self).__init__(complete=gdb.COMPLETE_NONE)
        self.breakpoints = []
        return

    def do_invoke(self, argv):
        if len(argv) < 1:
            self.usage()
            return

        action, module = argv[0].split(":", 1)
        if action=="ld":
            self.breakpoints.append(BreakOnLoadSharedLibrary(module))
        elif action=="ud":
            bkps = [bp for bp in self.breakpoints if bp.module_name == module]
            if len(bkps):
                bkp = bkps[0]
                bkp.enabled = False
                bkp.delete()
                bkps.remove(bkp)
        else:
            self.usage()
        return


class WindbgTcCommand(GenericCommand):
    """WinDBG compatibility layer: tc - trace to next call."""
    _cmdline_ = "tc"
    _syntax_  = "{:s} [COUNT]".format(_cmdline_)

    @only_if_gdb_running
    def do_invoke(self, argv):
        cnt = int(argv[0]) if len(argv) else 0xffffffffffffffff
        while cnt:
            cnt -= 1
            set_gef_setting("context.enable", False)
            gdb.execute("stepi")
            insn = gef_current_instruction(current_arch.pc)
            if current_arch.is_call(insn):
                break
        set_gef_setting("context.enable", True)
        gdb.execute("context")
        return


class WindbgPcCommand(GenericCommand):
    """WinDBG compatibility layer: pc - run until call."""
    _cmdline_ = "pc"
    _syntax_  = "{:s} [COUNT]".format(_cmdline_)

    @only_if_gdb_running
    def do_invoke(self, argv):
        cnt = int(argv[0]) if len(argv) else 0xffffffffffffffff
        while cnt:
            cnt -= 1
            set_gef_setting("context.enable", False)
            gdb.execute("nexti")
            insn = gef_current_instruction(current_arch.pc)
            if current_arch.is_call(insn):
                break

        set_gef_setting("context.enable", True)
        gdb.execute("context")
        return


class WindbgHhCommand(GenericCommand):
    """WinDBG compatibility layer: hh - open help in web browser."""
    _cmdline_ = "hh"
    _syntax_  = "{:s}".format(_cmdline_)

    def do_invoke(self, argv):
        url = "https://gef.readthedocs.io/en/master/"
        if len(argv):
            url += "search.html?q={}".format(argv[0])
        p = subprocess.Popen(["xdg-open", url],
                             cwd="/",
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        return


class WindbgGoCommand(GenericCommand):
    """WinDBG compatibility layer: g - go."""
    _cmdline_ = "g"
    _syntax_  = "{:s}".format(_cmdline_)

    def do_invoke(self, argv):
        if is_alive():
            gdb.execute("continue")
        else:
            gdb.execute("run {}".format(" ".join(argv)))
        return


class WindbgUCommand(GenericCommand):
    """WinDBG compatibility layer: u - disassemble."""
    _cmdline_ = "u"
    _syntax_  = "{:s}".format(_cmdline_)

    def __init__(self):
        super(WindbgUCommand, self).__init__(complete=gdb.COMPLETE_LOCATION)
        return

    @only_if_gdb_running
    def do_invoke(self, argv):
        length = 16
        location = current_arch.pc
        for arg in argv:
            if arg[0] in ("l","L"):
                length = int(arg[1:])
            else:
                location = safe_parse_and_eval(arg)
                if location is not None:
                    if hasattr(location, "address"):
                        location = int(location.address)
                    else:
                        location = int(location)

        for insn in gef_disassemble(location, length):
            print(insn)
        return


class WindbgXCommand(GenericCommand):
    """WinDBG compatibility layer: x - search symbol."""
    _cmdline_ = "xs"
    _syntax_  = "{:s} REGEX".format(_cmdline_)

    def __init__(self):
        super(WindbgXCommand, self).__init__(complete=gdb.COMPLETE_LOCATION)
        return

    def do_invoke(self, argv):
        if len(argv) < 1:
            err("Missing REGEX")
            return

        sym = argv[0]
        try:
            gdb.execute("info function {}".format(sym))
            gdb.execute("info address {}".format(sym))
        except gdb.error:
            pass
        return

class WindbgRCommand(GenericCommand):
    """WinDBG compatibility layer: r - register info"""
    _cmdline_ = "r"
    _syntax_  = "{:s} [REGISTER[=VALUE]]".format(_cmdline_)

    def print_regs(self, reg_list, n):
        def chunks(l, n):
            for ii in range(0, len(l), n):
                yield l[ii:ii + n]

        def print_reg(reg):
            print('%s=%016x' % (reg.rjust(3), get_register('$' + reg)), end='')

        for regs in chunks(reg_list, n):
            for ii in range(0, len(regs)):
                reg = regs[ii]

                if reg is not None: print_reg(reg)

                if ii + 1 != len(regs): print(' ', end='')
                else: print()


    def print_gprs(self):
        gprs = None

        if get_arch().startswith("i386:x86-64"):
            # rax=0000000000000000 rbx=000000e62e50b000 rcx=00007ffb4763c564
            # rdx=0000000000000000 rsi=00007ffb476cd4c0 rdi=0000000000000010
            # rip=00007ffb4767121c rsp=000000e62e28f140 rbp=0000000000000000
            #  r8=000000e62e28f138  r9=0000000000000000 r10=0000000000000000
            # r11=0000000000000246 r12=0000000000000001 r13=0000000000000000
            # r14=00007ffb476ccd90 r15=0000027685520000
            gprs = [
                'rax', 'rbx', 'rcx',
                'rdx', 'rsi', 'rdi',
                'rip', 'rsp', 'rbp',
                'r8', 'r9', 'r10',
                'r11', 'r12', 'r13',
                'r14', 'r15'
                ]
            self.print_regs(gprs, 3)
            return
        elif get_arch().startswith('aarch64'):
            #  x0=0000000000000078   x1=000002037b0069e0   x2=0000000000000010   x3=000000293a8ff9f0
            #  x4=000000293a8ffb90   x5=000000293a8ff9eb   x6=0000000000000000   x7=0000000000000000
            #  x8=0000000000000072   x9=0000000000000000  x10=0000000000000000  x11=ffffffffff817aa9
            # x12=00007ffea822efe0  x13=0000000000000967  x14=00007ffea8241b1e  x15=00007ffea822f008
            # x16=0000000000000000  x17=0000000000000000  x18=0000000000000000  x19=000002037b006d60
            # x20=000002037b0069e0  x21=000002037b004c10  x22=0000000000000010  x23=000000007ffe03c0
            # x24=0000000000000001  x25=0000000000000000  x26=000000293a8ff9e0  x27=0000000000000010
            # x28=0000000000000000   fp=000000293a8ffc10   lr=00007ffea80f7388   sp=000000293a8ff9e0
            #  pc=00007ffea80e30f4  psr=60000000 -ZC- EL0
            gprs = [
                'x0', 'x1', 'x2', 'x3',
                'x4', 'x5', 'x6', 'x7',
                'x8', 'x9', 'x10', 'x11',
                'x12', 'x13', 'x14', 'x15',
                'x16', 'x17', 'x18', 'x19',
                'x20', 'x21', 'x22', 'x23',
                'x24', 'x25', 'x26', 'x27',
                'x28', 'fp', 'lr', 'sp',
                'pc'
                ]
            self.print_regs(gprs, 4)
            return

        raise NotImplemented

    @only_if_gdb_running
    def do_invoke(self, argv):
        if len(argv) < 1:
            self.print_gprs()
        else:
            combined = ''.join(argv).replace(' ', '').replace('@', '')

            if '=' in combined:
                (regstr,valstr) = combined.split('=')
                reg = '$' + regstr
                val = int(valstr, 16)
                gdb.execute("set {:s} = {:#x}".format(reg, val))
            else:
                regs = combined.split(',')
                self.print_regs(regs)

        return



def __windbg_prompt__(current_prompt):
    """WinDBG prompt function."""
    p = "0:000 "
    p+="\u27a4  "

    if get_gef_setting("gef.readline_compat")==True or \
       get_gef_setting("gef.disable_color")==True:
        return gef_prompt

    if is_alive():
        return Color.colorify(p, attrs="bold green")
    else:
        return Color.colorify(p, attrs="bold red")


def __default_prompt__(x):
    if get_gef_setting("gef.use-windbg-prompt") == True:
        return __windbg_prompt__(x)
    else:
        return __gef_prompt__(x)


# Prompt
set_gef_setting("gef.use-windbg-prompt", False, bool, "Use WinDBG like prompt")
gdb.prompt_hook = __default_prompt__

# Aliases
GefAlias("da", "display/s", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("dt", "pcustom")
GefAlias("dq", "hexdump qword", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("dd", "hexdump dword", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("dw", "hexdump word", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("db", "hexdump byte", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("eq", "patch qword", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("ed", "patch dword", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("ew", "patch word", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("eb", "patch byte", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("ea", "patch string", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("dps", "dereference", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("bp", "break", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("bl", "info breakpoints")
GefAlias("bd", "disable breakpoints")
GefAlias("bc", "delete breakpoints")
GefAlias("be", "enable breakpoints")
GefAlias("tbp", "tbreak", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("s", "grep", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("pa", "advance", completer_class=gdb.COMPLETE_LOCATION)
GefAlias("kp", "info stack")
GefAlias("ptc", "finish")
GefAlias("uf", "disassemble")

# Commands
windbg_commands = [
    WindbgTcCommand,
    WindbgPcCommand,
    WindbgHhCommand,
    WindbgGoCommand,
    WindbgXCommand,
    WindbgUCommand,
    WindbgSxeCommand,
    WindbgRCommand,
]

for _ in windbg_commands: register_external_command(_())
