rule webshell_php_eval_combo
{
    meta:
        description = "PHP opening tag with eval/assert style sink"
        severity = "high"
        layer = "L1"
    strings:
        $php = "<?php" nocase
        $eval = "eval(" nocase
        $assert = "assert(" nocase
    condition:
        $php and 1 of ($eval, $assert)
}

rule webshell_php_system_combo
{
    meta:
        description = "PHP tag with system/exec style call"
        severity = "high"
        layer = "L1"
    strings:
        $php = "<?php" nocase
        $s1 = "system(" nocase
        $s2 = "shell_exec(" nocase
        $s3 = "passthru(" nocase
    condition:
        $php and 1 of ($s1, $s2, $s3)
}
