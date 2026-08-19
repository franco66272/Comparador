"""Ejecutor continuo del verificador incremental."""
import argparse, subprocess, sys, time
from datetime import datetime

BASE = __file__.rsplit('\\',1)[0] if '\\' in __file__ else __file__.rsplit('/',1)[0]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cada-minutos',type=int,default=15)
    ap.add_argument('--lote',type=int,default=120)
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--horas',type=float,default=12)
    args=ap.parse_args()
    print(f'Verificación continua activa: cada {args.cada_minutos} min | lote {args.lote} | cada producto no más de cada {args.horas:g} h')
    while True:
        print('\n'+'='*70)
        print(datetime.now().strftime('%d/%m/%Y %H:%M:%S'),'iniciando ciclo')
        subprocess.run([sys.executable,'verificar_precios.py','--lote',str(args.lote),'--workers',str(args.workers),'--horas',str(args.horas)], cwd=BASE, check=False)
        print('Próximo ciclo en',args.cada_minutos,'minutos')
        time.sleep(max(60,args.cada_minutos*60))

if __name__=='__main__':main()
