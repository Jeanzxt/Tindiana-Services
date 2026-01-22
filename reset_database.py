#!/usr/bin/env python3
"""
Script para resetar o banco de dados e criar novo usuário admin
Útil quando há problemas de autenticação ou para inicializar o sistema
"""

import os
import sys
from app import app, db, Usuario, inicializar_dados

def resetar_banco():
    """Reseta o banco de dados completamente"""
    with app.app_context():
        print("🗑️  Deletando banco de dados antigo...")
        db_path = 'instance/tindiana_sistema_final.db'
        
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"✓ Banco removido: {db_path}")
            except Exception as e:
                print(f"✗ Erro ao remover banco: {e}")
                return False
        
        print("\n🏗️  Criando novo banco de dados...")
        try:
            db.create_all()
            print("✓ Banco criado com sucesso!")
        except Exception as e:
            print(f"✗ Erro ao criar banco: {e}")
            return False
        
        print("\n👤 Criando usuário admin...")
        try:
            # Remover admin existente se houver
            admin_existente = Usuario.query.filter_by(username='admin').first()
            if admin_existente:
                db.session.delete(admin_existente)
                db.session.commit()
                print("  - Admin antigo removido")
            
            # Criar novo admin
            admin = Usuario(
                username='admin',
                email='admin@tindiana.com',
                nome_completo='Administrador Tindiana'
            )
            admin.set_senha('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✓ Usuário admin criado!")
            print("  - Usuário: admin")
            print("  - Senha: admin123")
        except Exception as e:
            print(f"✗ Erro ao criar admin: {e}")
            db.session.rollback()
            return False
        
        print("\n📦 Inicializando dados padrão...")
        try:
            inicializar_dados()
            print("✓ Dados padrão criados!")
        except Exception as e:
            print(f"✗ Erro ao inicializar dados: {e}")
            return False
        
        print("\n" + "="*50)
        print("✅ BANCO DE DADOS RESETADO COM SUCESSO!")
        print("="*50)
        print("\n🔐 Credenciais de acesso:")
        print("   Usuário: admin")
        print("   Senha: admin123")
        print("\n⚠️  AVISO: Mude a senha no sistema!")
        print("\n🚀 Para iniciar o servidor:")
        print("   python app.py")
        print("="*50 + "\n")
        
        return True

if __name__ == '__main__':
    print("\n" + "="*50)
    print("RESET DO BANCO DE DADOS - TINDIANA")
    print("="*50 + "\n")
    print("⚠️  AVISO: Esta ação vai:")
    print("   • Deletar o banco de dados atual")
    print("   • Criar um novo banco vazio")
    print("   • Criar usuário admin padrão")
    print("\n")
    
    confirmacao = input("Deseja continuar? (s/n): ").strip().lower()
    
    if confirmacao in ['s', 'sim', 'y', 'yes']:
        sucesso = resetar_banco()
        sys.exit(0 if sucesso else 1)
    else:
        print("Operação cancelada.")
        sys.exit(0)
