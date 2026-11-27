#!/usr/bin/env python3
"""Startup ordering doubles and no-cooldown source tests; optional exact APK."""
import argparse,ast,json
from pathlib import Path
import sys,types,unittest,zipfile
from patch_history_recovery import welcome,audit,WELCOME,AD
p=argparse.ArgumentParser();p.add_argument('--apk',type=Path);p.add_argument('--out',type=Path);args,rest=p.parse_known_args()
if args.apk:
    with zipfile.ZipFile(args.apk) as z:SOURCE=z.read(WELCOME).decode();RULE=z.read('assets/addons/service.smarted.bootstrap/ads_regra.py').decode()
else:
    SOURCE='''# local dispatcher fixture; exact original code is used with --apk.
def untouched_license():
    return 'preserve license validation'
def abrir_tela_entrada():
    _limpar(MARCA_VOLTAR)
    _limpar_guarda_de_saida()
    if ativacao_concluida():
        _ir_para_home('normal')
        return True
    if _veio_de_uma_saida():
        _ir_para_home('reentry')
        return True
    pasta = _pasta_da_tela()
    if not pasta:
        _ir_para_home('unavailable')
        return False
    janela = WelcomeDialog(_xml_da_tela(pasta), pasta, 'Default', '1080i')
    janela.doModal()
    _ir_para_home()
    return True
'''
    RULE=Path('android-build/ads-patches/ads_regra.py').read_text()
AFTER=welcome(SOURCE);EVIDENCE=[]

def execute(source,activated,exit_marker):
    events=[]
    class Dialog:
        def __init__(self,*a):events.append('existing-dialog-created')
        def doModal(self):events.extend(['existing-dialog-shown','existing-dialog-flow-finished'])
    env=dict(MARCA_VOLTAR='return',_limpar=lambda *a:None,_limpar_guarda_de_saida=lambda:None,
        ativacao_concluida=lambda:activated,_veio_de_uma_saida=lambda:exit_marker,
        _limpar_marca_de_saida=lambda:None,_ir_para_home=lambda *a:events.append('home'),
        _pasta_da_tela=lambda:'unchanged-original-skin',_xml_da_tela=lambda p:'original.xml',
        WelcomeDialog=Dialog,_log=lambda *a:None,xbmc=types.SimpleNamespace(LOGERROR=3))
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='abrir_tela_entrada')
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<startup-dispatcher>','exec'),env)
    env['abrir_tela_entrada']();return events

class Startup(unittest.TestCase):
    def test_before_reproduces_skip_with_activated_state(self):self.assertEqual(execute(SOURCE,True,False),['home'])
    def test_before_reproduces_skip_with_exit_state(self):self.assertEqual(execute(SOURCE,False,True),['home'])
    def test_after_shows_existing_dialog_before_home_for_all_states(self):
        for activated in (False,True):
            for exit_marker in (False,True):
                before=execute(SOURCE,activated,exit_marker);after=execute(AFTER,activated,exit_marker)
                EVIDENCE.append(dict(activated_fixture=activated,reentry_fixture=exit_marker,before=before,after=after,kind='doubles-not-native-UI'))
                self.assertLess(after.index('existing-dialog-shown'),after.index('home'))
                self.assertLess(after.index('existing-dialog-flow-finished'),after.index('home'))
    def test_other_bytes_including_license_and_layout_logic_unchanged(self):audit(SOURCE,AFTER,'abrir_tela_entrada')
    def test_no_cooldown_for_new_contents_even_one_second_apart(self):
        fn=next(n for n in ast.parse(RULE).body if isinstance(n,ast.FunctionDef) and n.name=='pode_anunciar')
        env={'_ler':lambda:dict(conteudo='previous',tentativa='previous',anunciado=True)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<current-rule>','exec'),env)
        for n in range(1,8):self.assertTrue(env['pode_anunciar']('content-'+str(n),1000+n)[0])
    def test_exact_apk_interval_zero(self):
        if not args.apk:self.skipTest('APK constant audited in cloud build')
        constants={t.id:ast.literal_eval(n.value) for n in ast.parse(RULE).body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name) and t.id=='INTERVALO'}
        self.assertEqual(constants['INTERVALO'],0)

if __name__=='__main__':
    result=unittest.main(argv=[sys.argv[0]]+rest,exit=False)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(EVIDENCE,indent=2)+'\n')
        print('::notice title=Startup before after ordering::'+json.dumps(EVIDENCE))
    sys.exit(not result.result.wasSuccessful())
