// Adds a "korean" entry to the Steam launcher (4249100_Launcher.exe).
//
// The launcher hard-codes four languages (english, french, german,
// japanese), each a folder next to it. This adds a fifth, "korean", that
// starts korean\Biohazard.exe and otherwise behaves like japanese
// (same registry key, same .reg file).
//
// usage: launcher_patch <original exe> <output exe>
using System;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;
using Mono.Cecil.Rocks;

static class Program
{
    const string Lang = "korean";

    static int Main(string[] args)
    {
        var asm = AssemblyDefinition.ReadAssembly(args[0]);
        var form = asm.MainModule.Types.Single(t => t.FullName == "RE1_LauncherForm.Form1");
        MethodDefinition M(string name) => form.Methods.Single(m => m.Name == name);

        int arrays = 0;
        foreach (var name in new[] { "InitializeComponent", "WriteIniSetting" })
            arrays += AppendToLanguageArrays(M(name));
        if (arrays != 2)
            throw new Exception("language arrays: found " + arrays);
        PatchSelectedIndexChanged(M("ComboBox1_SelectedIndexChanged"));
        PatchStart(M("button2_Click"));
        PatchCheckRegistry(M("checkRegistry"));

        asm.Write(args[1]);
        Console.WriteLine("launcher: added '" + Lang + "'");
        return 0;
    }

    static bool IsLdstr(Instruction i, string s) => i.OpCode == OpCodes.Ldstr && (string)i.Operand == s;

    // { "english", "french", "german", "japanese" } -> + "korean"
    static int AppendToLanguageArrays(MethodDefinition m)
    {
        var body = m.Body;
        body.SimplifyMacros();
        var il = body.GetILProcessor();
        int n = 0;
        foreach (var ja in body.Instructions.Where(i => IsLdstr(i, "japanese")).ToList()) {
            var store = ja.Next;
            if (store.OpCode != OpCodes.Stelem_Ref)
                continue;
            // the array length is the ldc.i4 4 before the newarr
            var p = ja;
            while (p.OpCode != OpCodes.Newarr)
                p = p.Previous;
            var len = p.Previous;
            if (len.OpCode != OpCodes.Ldc_I4 || (int)len.Operand != 4)
                throw new Exception(m.Name + ": unexpected array length");
            len.Operand = 5;
            il.InsertAfter(store, il.Create(OpCodes.Stelem_Ref));
            il.InsertAfter(store, il.Create(OpCodes.Ldstr, Lang));
            il.InsertAfter(store, il.Create(OpCodes.Ldc_I4, 4));
            il.InsertAfter(store, il.Create(OpCodes.Dup));
            n++;
        }
        body.OptimizeMacros();
        return n;
    }

    static Instruction Switch(MethodBody body)
    {
        var sw = body.Instructions.Single(i => i.OpCode == OpCodes.Switch);
        if (((Instruction[])sw.Operand).Length != 4)
            throw new Exception("unexpected switch");
        return sw;
    }

    // case 4: text = "korean"; -> saved as LanguageSetting in the launcher ini
    static void PatchSelectedIndexChanged(MethodDefinition m)
    {
        var body = m.Body;
        body.SimplifyMacros();
        var il = body.GetILProcessor();
        var sw = Switch(body);
        var targets = (Instruction[])sw.Operand;
        var join = targets[3].Next.Next;              // after: ldstr "japanese"; stloc.1
        // appended after the final ret, reachable only through the switch
        var k0 = il.Create(OpCodes.Ldstr, Lang);
        il.Append(k0);
        il.Append(il.Create(OpCodes.Stloc, body.Variables[1]));
        il.Append(il.Create(OpCodes.Br, join));
        sw.Operand = targets.Concat(new[] { k0 }).ToArray();
        body.OptimizeMacros();
    }

    // case 4: start korean\Biohazard.exe
    static void PatchStart(MethodDefinition m)
    {
        var body = m.Body;
        body.SimplifyMacros();
        var il = body.GetILProcessor();
        var sw = Switch(body);
        var targets = (Instruction[])sw.Operand;
        // copy the japanese case (newobj ... ret) with a different working directory
        var block = new System.Collections.Generic.List<Instruction>();
        for (var i = targets[3]; ; i = i.Next) {
            var c = i.Operand == null ? il.Create(i.OpCode) : CloneWithOperand(il, i);
            if (IsLdstr(i, ".\\japanese\\"))
                c = il.Create(OpCodes.Ldstr, ".\\" + Lang + "\\");
            block.Add(c);
            if (i.OpCode == OpCodes.Ret)
                break;
        }
        if (!block.Any(i => IsLdstr(i, ".\\" + Lang + "\\")))
            throw new Exception("button2_Click: japanese case not found");
        foreach (var c in block)
            il.Append(c);
        sw.Operand = targets.Concat(new[] { block[0] }).ToArray();
        body.OptimizeMacros();
    }

    static Instruction CloneWithOperand(ILProcessor il, Instruction i)
    {
        switch (i.Operand) {
        case MethodReference mr: return il.Create(i.OpCode, mr);
        case string s: return il.Create(i.OpCode, s);
        case TypeReference tr: return il.Create(i.OpCode, tr);
        case FieldReference fr: return il.Create(i.OpCode, fr);
        default: throw new Exception("cannot clone " + i);
        }
    }

    // num = comboBox1.SelectedIndex; if (num == 4) num = 3;
    static void PatchCheckRegistry(MethodDefinition m)
    {
        var body = m.Body;
        body.SimplifyMacros();
        var il = body.GetILProcessor();
        var get = body.Instructions.First(i => i.OpCode == OpCodes.Callvirt &&
                                               ((MethodReference)i.Operand).Name == "get_SelectedIndex");
        var st = get.Next;
        if (st.OpCode != OpCodes.Stloc || ((VariableDefinition)st.Operand).Index != 0)
            throw new Exception("checkRegistry: unexpected code");
        var after = st.Next;
        var num = body.Variables[0];
        il.InsertBefore(after, il.Create(OpCodes.Ldloc, num));
        il.InsertBefore(after, il.Create(OpCodes.Ldc_I4, 4));
        il.InsertBefore(after, il.Create(OpCodes.Bne_Un, after));
        il.InsertBefore(after, il.Create(OpCodes.Ldc_I4, 3));
        il.InsertBefore(after, il.Create(OpCodes.Stloc, num));
        body.OptimizeMacros();
    }
}
