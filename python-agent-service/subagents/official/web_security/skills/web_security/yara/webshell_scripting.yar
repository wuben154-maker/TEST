rule webshell_python_exec_import
{
    meta:
        description = "Python subprocess or dangerous import patterns"
        severity = "high"
        layer = "L1"
    strings:
        $s1 = "subprocess" nocase
        $s2 = "os.system" nocase
        $s3 = "__import__" nocase
        $s4 = "eval(" nocase
    condition:
        2 of them
}

rule webshell_jsp_runtime
{
    meta:
        description = "JSP scriptlet with Java runtime exec"
        severity = "high"
        layer = "L1"
    strings:
        $j = "<%" nocase
        $r = "Runtime" nocase
        $e = "exec(" nocase
    condition:
        $j and $r and $e
}
