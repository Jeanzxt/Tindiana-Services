#!/usr/bin/env python3
"""
Script de diagnóstico - identifica bugs do sistema
"""

import sys
import os

print("\n" + "="*60)
print("DIAGNÓSTICO DO SISTEMA TINDIANA")
print("="*60 + "\n")

# 1. Verificar imports
print("✓ Testando imports...")
try:
    from app import app, db, Usuario, Produto, Fornecedor, Requisicao, Cotacao
    print("  ✓ App imports OK")
except ImportError as e:
    print(f"  ✗ Erro nos imports: {e}")
    sys.exit(1)

# 2. Verificar banco de dados
print("\n✓ Testando banco de dados...")
try:
    with app.app_context():
        # Criar tabelas
        db.create_all()
        print("  ✓ Banco de dados criado/verificado")
        
        # Verificar se tabela Usuario existe
        usuario_count = Usuario.query.count()
        print(f"  ✓ Usuários no banco: {usuario_count}")
        
        # Listar usuários
        if usuario_count > 0:
            usuarios = Usuario.query.all()
            print(f"\n  Usuários cadastrados:")
            for u in usuarios:
                print(f"    - {u.username} ({u.email})")
        else:
            print("  ⚠️  Nenhum usuário encontrado!")
            print("  Criando usuário admin padrão...")
            
            admin = Usuario(
                username='admin',
                email='admin@tindiana.com',
                nome_completo='Administrador Tindiana'
            )
            admin.set_senha('admin123')
            db.session.add(admin)
            db.session.commit()
            print("  ✓ Usuário admin criado!")
            
except Exception as e:
    print(f"  ✗ Erro no banco: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. Verificar templates
print("\n✓ Testando templates...")
template_dir = 'templates'
templates = [
    'login.html',
    'base.html',
    'dashboard.html',
    'admin_criar_usuario.html'
]

for template in templates:
    path = os.path.join(template_dir, template)
    if os.path.exists(path):
        print(f"  ✓ {template}")
    else:
        print(f"  ✗ {template} - FALTANDO!")

# 4. Verificar pastas estáticas
print("\n✓ Testando arquivos estáticos...")
static_files = [
    'static/css/style.css',
    'static/js/main.js'
]

for file in static_files:
    if os.path.exists(file):
        print(f"  ✓ {file}")
    else:
        print(f"  ✗ {file} - FALTANDO!")

# 5. Testar rotas
print("\n✓ Testando rotas...")
try:
    with app.test_client() as client:
        # Testar acesso à home (deve redirecionar para login)
        response = client.get('/')
        print(f"  ✓ GET / - Status: {response.status_code}")
        
        # Testar login
        response = client.get('/login')
        if response.status_code == 200:
            print(f"  ✓ GET /login - Status: {response.status_code}")
        else:
            print(f"  ✗ GET /login - Status: {response.status_code}")
            
except Exception as e:
    print(f"  ✗ Erro ao testar rotas: {e}")

print("\n" + "="*60)
print("DIAGNÓSTICO CONCLUÍDO!")
print("="*60)
print("\n📝 Próximos passos:")
print("  1. Se todos os testes passaram, o servidor está OK")
print("  2. Execute: python app.py")
print("  3. Acesse: http://localhost:5000")
print("="*60 + "\n")
