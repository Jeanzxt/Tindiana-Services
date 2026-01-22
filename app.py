from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
import re
from decimal import Decimal
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

app = Flask(__name__)

# Configuração
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tindiana_sistema_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'chave_super_secreta_tindiana_2024_dev')

db = SQLAlchemy(app)

# --- TABELA DE ASSOCIAÇÃO (Muitos-para-Muitos) ---
requisicao_fornecedores_table = db.Table('requisicao_fornecedores',
    db.Column('requisicao_id', db.Integer, db.ForeignKey('requisicao.id'), primary_key=True),
    db.Column('fornecedor_id', db.Integer, db.ForeignKey('fornecedor.id'), primary_key=True),
    db.Column('preco_fornecedor', db.Float, nullable=True)
)

# --- MODELOS (TODOS DEFINIDOS AQUI) ---
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    nome_completo = db.Column(db.String(150))
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    ultimo_acesso = db.Column(db.DateTime)
    
    def set_senha(self, senha):
        """Define a senha com hash"""
        self.senha_hash = generate_password_hash(senha)
    
    def verifica_senha(self, senha):
        """Verifica se a senha está correta"""
        return check_password_hash(self.senha_hash, senha)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    categoria = db.Column(db.String(50), default='Geral')
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    cotacoes = db.relationship('Cotacao', backref='produto', lazy=True, cascade='all, delete-orphan')
    requisicoes = db.relationship('Requisicao', backref='produto', lazy=True, cascade='all, delete-orphan')

class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    contato = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.now)
    cotacoes = db.relationship('Cotacao', backref='fornecedor', lazy=True, cascade='all, delete-orphan')

class Requisicao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, default=1)
    data_pedido = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='Pendente')
    prioridade = db.Column(db.String(10), default='Normal')
    
    fornecedores_selecionados = db.relationship('Fornecedor', 
                                              secondary=requisicao_fornecedores_table,
                                              lazy='subquery',
                                              backref=db.backref('requisicoes', lazy=True))
    
class Cotacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    preco = db.Column(db.Float, nullable=False)
    data_cotacao = db.Column(db.Date, default=datetime.now)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=False)
    requisicao_origem_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default='Aprovada')
    
    def get_alerta_preco(self):
        """Retorna alerta de preço baseado na média histórica"""
        media_produto = db.session.query(
            db.func.avg(Cotacao.preco)
        ).filter(Cotacao.produto_id == self.produto_id).scalar() or 0
        
        if media_produto == 0:
            return {'tipo': 'normal', 'emoji': '📊', 'label': 'Novo'}
        
        percentual_diff = ((self.preco - media_produto) / media_produto) * 100
        
        if percentual_diff < -10:
            return {'tipo': 'bom', 'emoji': '✅', 'label': 'Preço Bom'}
        elif percentual_diff > 15:
            return {'tipo': 'alto', 'emoji': '⚠️', 'label': 'Preço Alto'}
        else:
            return {'tipo': 'normal', 'emoji': '📊', 'label': 'Normal'}

# --- FUNÇÕES AUXILIARES ---
def formatar_moeda(valor):
    """Formata valor para exibição em reais"""
    try:
        return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return "R$ 0,00"

def parse_moeda(valor_str):
    """Converte string de moeda para float"""
    try:
        if not valor_str:
            return None
        valor_str = valor_str.replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(valor_str)
    except ValueError:
        return None

def analisar_alerta_preco(cotacao_atual):
    """Analisa se o preço de uma cotação é bom ou alto"""
    # Calcular média histórica de preços para esse produto
    media_produto = db.session.query(
        db.func.avg(Cotacao.preco)
    ).filter(Cotacao.produto_id == cotacao_atual.produto_id).scalar() or 0
    
    if media_produto == 0:
        return {'tipo': 'normal', 'emoji': '📊', 'label': 'Novo'}
    
    percentual_diff = ((cotacao_atual.preco - media_produto) / media_produto) * 100
    
    if percentual_diff < -10:
        return {'tipo': 'bom', 'emoji': '✅', 'label': 'Preço Bom'}
    elif percentual_diff > 15:
        return {'tipo': 'alto', 'emoji': '⚠️', 'label': 'Preço Alto'}
    else:
        return {'tipo': 'normal', 'emoji': '📊', 'label': 'Normal'}

def validar_codigo_produto(codigo):
    """Valida se o código do produto é válido"""
    try:
        codigo_int = int(codigo)
        if codigo_int <= 0:
            return False, "Código deve ser maior que zero"
        return True, ""
    except ValueError:
        return False, "Código deve ser um número"

# --- DECORADOR DE AUTENTICAÇÃO ---
def login_obrigatorio(f):
    """Decorador para proteger rotas que exigem autenticação"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Você precisa fazer login para acessar esta página!', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- INICIALIZAÇÃO DE DADOS ---
def inicializar_dados():
    """Inicializa o banco com dados padrão"""
    
    # Criar usuário padrão se não existir
    usuario_admin = Usuario.query.filter_by(username='admin').first()
    if not usuario_admin:
        admin = Usuario(
            username='admin',
            email='admin@tindiana.com',
            nome_completo='Administrador'
        )
        admin.set_senha('admin123')
        db.session.add(admin)
    
    # Produtos padrão
    itens_padrao = [
        (2289, "BORRACHA SUPORTE PARALAMA SCANIA"),
        (1687, "KIT COXIM 5 RODA"),
        (1070, "BORRACHA SUPORTE PARALAMA VOLVO"),
        (2350, "LIXA ROQUITE 80"),
        (975, "OLEO 5W20"),
        (515, "ANEL BUCHA DO TIRANTE"),
        (2200, "ABRACADEIRA NYLON 7,2/40CM"),
        (3, "DISCO FLAP 7''"),
        (8, "FILTRO RACOR"),
        (2567, "ARCO DE LONA 2,48"),
        (1280, "MOLA SUSPENSÃO DIANTEIRA"),
        (890, "PASTILHA FREIO DIANTEIRO"),
        (345, "FILTRO DE ÓLEO"),
        (1678, "VELA DE IGNIÇÃO"),
        (2450, "CORREIA DENTADA"),
        (1123, "BATERIA 12V 60AH"),
        (789, "LÂMPADA FAROL DIANTEIRO"),
        (456, "SENSOR ABS"),
        (2345, "EMBREAGEM COMPLETA"),
        (678, "RADIADOR ÁGUA")
    ]
    
    count_prod = 0
    for id_prod, nome_prod in itens_padrao:
        if not Produto.query.get(id_prod):
            p = Produto(id=id_prod, nome=nome_prod.strip())
            db.session.add(p)
            count_prod += 1
    
    # Fornecedores padrão
    fornecedores_padrao = [
        "RANDON PEÇAS",
        "MERCADO AUTOMOTIVO LTDA",
        "AUTO CENTER SCANIA",
        "VOLVO PARTS BRASIL",
        "PEÇAS PESADAS S.A.",
        "DISTRIBUIDORA CAMINHÕES",
        "MECÂNICA INDUSTRIAL",
        "FORNECEDOR OFICIAL MERCEDES",
        "SUPRIMENTOS TRUCK",
        "IMPORTADORA DE AUTOPEÇAS"
    ]
    
    count_forn = 0
    for nome_forn in fornecedores_padrao:
        if not Fornecedor.query.filter_by(nome=nome_forn).first():
            f = Fornecedor(nome=nome_forn)
            db.session.add(f)
            count_forn += 1
    
    if count_prod > 0 or count_forn > 0:
        db.session.commit()
        print(f"Dados inicializados: {count_prod} produtos e {count_forn} fornecedores adicionados.")

# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_data():
    """Injeta dados globais em todos os templates"""
    return {
        'current_date': datetime.now().strftime('%d/%m/%Y'),
        'formatar_moeda': formatar_moeda,
        'len': len
    }

# --- ROTAS GERAIS ---
@app.route('/')
def index():
    """Redireciona para dashboard ou login"""
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        senha = request.form.get('senha', '')
        
        if not username or not senha:
            flash('Usuário e senha são obrigatórios!', 'error')
            return redirect(url_for('login'))
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.verifica_senha(senha) and usuario.ativo:
            # Registrar acesso
            usuario.ultimo_acesso = datetime.now()
            db.session.commit()
            
            # Iniciar sessão
            session['usuario_id'] = usuario.id
            session['username'] = usuario.username
            session['nome'] = usuario.nome_completo or usuario.username
            
            flash(f'Bem-vindo, {usuario.nome_completo or usuario.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha inválidos!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout do usuário"""
    session.clear()
    flash('Você foi desconectado!', 'success')
    return redirect(url_for('login'))

@app.route('/ranking')
@login_obrigatorio
def ranking():
    """Página de ranking de fornecedores com scores"""
    fornecedores = Fornecedor.query.filter_by(ativo=True).all()
    
    ranking_data = []
    
    for fornecedor in fornecedores:
        cotacoes = Cotacao.query.filter_by(fornecedor_id=fornecedor.id).all()
        
        if not cotacoes:
            continue
        
        # 1. Score de Preço: fornecedores mais baratos têm maior score
        todos_precos = db.session.query(db.func.avg(Cotacao.preco)).scalar() or 0
        preco_medio = sum(c.preco for c in cotacoes) / len(cotacoes)
        
        if todos_precos > 0:
            score_preco = max(0, 10 - ((preco_medio - todos_precos) / todos_precos * 10))
        else:
            score_preco = 5
        
        # 2. Score de Confiabilidade: baseado em vitórias (cotações ganhas)
        vitoria_rate = len(cotacoes) / max(1, Cotacao.query.count()) * 100
        score_confiabilidade = min(10, (vitoria_rate / 100) * 10 + 3)
        
        # 3. Score de Consistência: quanto menor a variação, melhor
        if len(cotacoes) > 1:
            preco_min = min(c.preco for c in cotacoes)
            preco_max = max(c.preco for c in cotacoes)
            variacao = preco_max - preco_min
            score_consistencia = max(1, 10 - (variacao / preco_medio * 5))
        else:
            score_consistencia = 8
        
        # Score total (média ponderada)
        score_total = (score_preco * 0.4 + score_confiabilidade * 0.35 + score_consistencia * 0.25)
        
        ranking_data.append({
            'fornecedor': {
                'id': fornecedor.id,
                'nome': fornecedor.nome
            },
            'qtd_cotacoes': len(cotacoes),
            'preco_medio': preco_medio,
            'score_total': round(score_total, 1),
            'score_preco': round(score_preco, 1),
            'score_confiabilidade': round(score_confiabilidade, 1),
            'score_consistencia': round(score_consistencia, 1),
            'variacao_preco': max(c.preco for c in cotacoes) - min(c.preco for c in cotacoes) if len(cotacoes) > 1 else 0
        })
    
    # Ordenar por score total
    ranking_data.sort(key=lambda x: x['score_total'], reverse=True)
    
    # Adicionar medalhas
    medalhas = ['🥇', '🥈', '🥉']
    for i, item in enumerate(ranking_data[:3]):
        item['medalha'] = medalhas[i]
    
    return render_template('ranking.html', ranking_data=ranking_data)

@app.route('/comparador')
@login_obrigatorio
def comparador():
    """Página de comparação de fornecedores"""
    fornecedor_ids = request.args.getlist('fornecedor')
    
    # Se não houver fornecedores selecionados, mostrar todos
    if not fornecedor_ids:
        fornecedores = Fornecedor.query.filter_by(ativo=True).all()[:10]
    else:
        try:
            fornecedor_ids = [int(f) for f in fornecedor_ids]
            fornecedores = Fornecedor.query.filter(Fornecedor.id.in_(fornecedor_ids)).all()
        except:
            fornecedores = Fornecedor.query.filter_by(ativo=True).all()[:10]
    
    # Obter estatísticas de cada fornecedor
    dados_comparacao = []
    
    for fornecedor in fornecedores[:5]:  # Limitar a 5 fornecedores
        cotacoes = Cotacao.query.filter_by(fornecedor_id=fornecedor.id).all()
        
        if cotacoes:
            preco_medio = sum(c.preco for c in cotacoes) / len(cotacoes)
            preco_min = min(c.preco for c in cotacoes)
            preco_max = max(c.preco for c in cotacoes)
            
            # Histórico dos últimos 10 preços
            historico = sorted(cotacoes, key=lambda x: x.data_cotacao, reverse=True)[:10]
            historico_preco = [c.preco for c in reversed(historico)]
            
            dados_comparacao.append({
                'fornecedor': {
                    'id': fornecedor.id,
                    'nome': fornecedor.nome
                },
                'qtd_cotacoes': len(cotacoes),
                'preco_medio': preco_medio,
                'preco_min': preco_min,
                'preco_max': preco_max,
                'historico_preco': historico_preco
            })
    
    # Todos os fornecedores para seleção
    todos_fornecedores = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    
    return render_template('comparador.html',
                         dados_comparacao=dados_comparacao,
                         todos_fornecedores=todos_fornecedores,
                         fornecedor_ids=fornecedor_ids)
@login_obrigatorio
def api_buscar():
    """API de busca rápida em tempo real"""
    termo = request.args.get('q', '').strip().lower()
    
    if not termo or len(termo) < 2:
        return jsonify([])
    
    resultados = []
    
    # Buscar em fornecedores
    fornecedores = Fornecedor.query.filter(
        Fornecedor.nome.ilike(f'%{termo}%'),
        Fornecedor.ativo == True
    ).limit(5).all()
    
    for f in fornecedores:
        resultados.append({
            'tipo': 'Fornecedor',
            'titulo': f.nome,
            'url': f'/fornecedores',
            'icon': 'fas fa-truck',
            'cor': '#ff6b6b'
        })
    
    # Buscar em produtos
    produtos = Produto.query.filter(
        Produto.nome.ilike(f'%{termo}%'),
        Produto.ativo == True
    ).limit(5).all()
    
    for p in produtos:
        resultados.append({
            'tipo': 'Produto',
            'titulo': p.nome,
            'url': f'/produtos',
            'icon': 'fas fa-box',
            'cor': '#4ecdc4'
        })
    
    # Buscar em cotações (últimas)
    cotacoes = db.session.query(
        Cotacao, Produto, Fornecedor
    ).join(Produto).join(Fornecedor).filter(
        (Produto.nome.ilike(f'%{termo}%')) | 
        (Fornecedor.nome.ilike(f'%{termo}%'))
    ).order_by(Cotacao.data_cotacao.desc()).limit(5).all()
    
    for cot, prod, forn in cotacoes:
        resultados.append({
            'tipo': 'Cotação',
            'titulo': f'{prod.nome} - {forn.nome}',
            'descricao': f'R$ {cot.preco:.2f}',
            'url': f'/historico_cotacoes',
            'icon': 'fas fa-receipt',
            'cor': '#a8e6cf'
        })
    
    return jsonify(resultados[:10])

@app.route('/admin/criar_usuario', methods=['GET', 'POST'])
def admin_criar_usuario():
    """Criar novo usuário (apenas para desenvolvimento)"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        nome_completo = request.form.get('nome_completo', '').strip()
        
        # Validações
        if not all([username, email, senha]):
            flash('Usuário, email e senha são obrigatórios!', 'error')
            return redirect(url_for('admin_criar_usuario'))
        
        if len(senha) < 6:
            flash('Senha deve ter pelo menos 6 caracteres!', 'error')
            return redirect(url_for('admin_criar_usuario'))
        
        # Verificar se usuário já existe
        usuario_existente = Usuario.query.filter_by(username=username).first()
        if usuario_existente:
            flash(f'Usuário "{username}" já existe!', 'error')
            return redirect(url_for('admin_criar_usuario'))
        
        # Verificar se email já existe
        email_existente = Usuario.query.filter_by(email=email).first()
        if email_existente:
            flash(f'Email "{email}" já está cadastrado!', 'error')
            return redirect(url_for('admin_criar_usuario'))
        
        try:
            novo_usuario = Usuario(
                username=username,
                email=email,
                nome_completo=nome_completo or username
            )
            novo_usuario.set_senha(senha)
            db.session.add(novo_usuario)
            db.session.commit()
            
            flash(f'Usuário "{username}" criado com sucesso!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar usuário: {str(e)}', 'error')
    
    return render_template('admin_criar_usuario.html')

@app.route('/dashboard')
@login_obrigatorio
def dashboard():
    """Página principal do sistema"""
    t_prod = Produto.query.filter_by(ativo=True).count()
    t_req_pend = Requisicao.query.filter_by(status='Pendente').count()
    t_cot = Cotacao.query.count()
    
    # Buscar últimas 10 cotações
    ultimas = Cotacao.query.order_by(Cotacao.data_cotacao.desc()).limit(10).all()
    
    # Estatísticas adicionais
    fornecedores_ativos = Fornecedor.query.filter_by(ativo=True).count()
    hoje = date.today()
    cotacoes_hoje = Cotacao.query.filter_by(data_cotacao=hoje).count()
    
    # Calcular dados para gráficos
    # 1. Distribuição de cotações por fornecedor
    cotacoes_por_forn = db.session.query(
        Fornecedor.nome,
        db.func.count(Cotacao.id)
    ).join(Cotacao, Fornecedor.id == Cotacao.fornecedor_id).group_by(Fornecedor.nome).all()
    
    labels_forn = [item[0] for item in cotacoes_por_forn]
    dados_forn = [item[1] for item in cotacoes_por_forn]
    
    # 2. Top 5 fornecedores por valor total
    top_fornecedores = db.session.query(
        Fornecedor.nome,
        db.func.sum(Cotacao.preco).label('total_valor')
    ).join(Cotacao, Fornecedor.id == Cotacao.fornecedor_id).group_by(Fornecedor.nome).order_by(
        db.desc('total_valor')
    ).limit(5).all()
    
    labels_top = [item[0] for item in top_fornecedores]
    dados_top = [float(item[1] or 0) for item in top_fornecedores]
    
    # 3. KPIs Executivos
    # Total gasto
    total_gasto = db.session.query(db.func.sum(Cotacao.preco)).scalar() or 0
    
    # Ticket médio
    ticket_medio = total_gasto / t_cot if t_cot > 0 else 0
    
    # Fornecedor mais usado
    fornecedor_top = db.session.query(
        Fornecedor.nome,
        db.func.count(Cotacao.id).label('count')
    ).join(Cotacao, Fornecedor.id == Cotacao.fornecedor_id).group_by(Fornecedor.nome).order_by(
        db.desc('count')
    ).first()
    
    fornecedor_top_nome = fornecedor_top[0] if fornecedor_top else "N/A"
    fornecedor_top_count = fornecedor_top[1] if fornecedor_top else 0
    
    # Preço máximo e mínimo
    preco_max = db.session.query(db.func.max(Cotacao.preco)).scalar() or 0
    preco_min = db.session.query(db.func.min(Cotacao.preco)).scalar() or 0
    
    # 4. Tendência de preços ao longo do tempo (últimos 30 dias)
    from sqlalchemy import func as sqla_func
    trinta_dias_atras = datetime.now() - timedelta(days=30)
    
    tendencias = db.session.query(
        Cotacao.data_cotacao,
        Fornecedor.nome,
        sqla_func.avg(Cotacao.preco)
    ).join(Fornecedor, Fornecedor.id == Cotacao.fornecedor_id).filter(
        Cotacao.data_cotacao >= trinta_dias_atras.date()
    ).group_by(Cotacao.data_cotacao, Fornecedor.nome).order_by(Cotacao.data_cotacao).all()
    
    # Organizar dados de tendência por fornecedor
    tendencia_dict = {}
    datas_unicas = set()
    
    for data, forn, preco_medio in tendencias:
        if forn not in tendencia_dict:
            tendencia_dict[forn] = {}
        tendencia_dict[forn][str(data)] = float(preco_medio or 0)
        datas_unicas.add(str(data))
    
    labels_datas = sorted(list(datas_unicas))
    # Pegar os 5 fornecedores com mais cotações recentes
    fornecedores_tendencia = list(tendencia_dict.keys())[:5]
    
    dados_tendencias = {}
    cores_fornecedores = ['#e40c0c', '#ff0000', '#b80000', '#ff6b6b', '#ff9999']
    
    for idx, forn in enumerate(fornecedores_tendencia):
        dados_forn = [tendencia_dict[forn].get(data, None) for data in labels_datas]
        dados_tendencias[forn] = {
            'dados': dados_forn,
            'cor': cores_fornecedores[idx % len(cores_fornecedores)]
        }
    
    return render_template('dashboard.html', 
                         t_prod=t_prod, 
                         t_req_pend=t_req_pend, 
                         t_cot=t_cot,
                         ultimas=ultimas,
                         fornecedores_ativos=fornecedores_ativos,
                         cotacoes_hoje=cotacoes_hoje,
                         labels_forn=labels_forn,
                         dados_forn=dados_forn,
                         labels_top=labels_top,
                         dados_top=dados_top,
                         total_gasto=total_gasto,
                         ticket_medio=ticket_medio,
                         fornecedor_top_nome=fornecedor_top_nome,
                         fornecedor_top_count=fornecedor_top_count,
                         preco_max=preco_max,
                         preco_min=preco_min,
                         labels_datas=labels_datas,
                         dados_tendencias=dados_tendencias)

# --- PRODUTOS ---
@app.route('/produtos', methods=['GET', 'POST'])
@login_obrigatorio
def produtos():
    """Gestão de produtos"""
    if request.method == 'POST':
        try:
            id_prod = request.form.get('id')
            nome = request.form.get('nome', '').strip()
            
            # Validações
            if not id_prod or not nome:
                flash('Código e descrição são obrigatórios!', 'error')
                return redirect(url_for('produtos'))
            
            if len(nome) < 3:
                flash('Descrição muito curta!', 'error')
                return redirect(url_for('produtos'))
            
            # Validar código
            valido, mensagem = validar_codigo_produto(id_prod)
            if not valido:
                flash(mensagem, 'error')
                return redirect(url_for('produtos'))
            
            id_prod = int(id_prod)
            
            # Verificar se código já existe
            if Produto.query.get(id_prod):
                flash('Erro: Código já existe!', 'error')
            else:
                novo_produto = Produto(id=id_prod, nome=nome)
                db.session.add(novo_produto)
                db.session.commit()
                flash(f'Item #{id_prod} cadastrado com sucesso!', 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar item: {str(e)}', 'error')
        
        return redirect(url_for('produtos'))
    
    # GET: Listar produtos
    produtos_lista = Produto.query.order_by(Produto.nome).all()
    return render_template('produtos.html', produtos=produtos_lista)

@app.route('/produto/editar/<int:id>', methods=['GET', 'POST'])
@login_obrigatorio
def editar_produto(id):
    """Editar produto existente"""
    prod = Produto.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            novo_nome = request.form.get('nome', '').strip()
            if not novo_nome:
                flash('Descrição não pode ser vazia!', 'error')
                return redirect(url_for('editar_produto', id=id))
            
            prod.nome = novo_nome
            db.session.commit()
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('produtos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar: {str(e)}', 'error')
    
    return render_template('editar_generico.html', tipo='Produto', item=prod)

@app.route('/novo_item')
@login_obrigatorio
def novo_item():
    """Redireciona para o fluxo novo"""
    return redirect(url_for('adicionar_item'))

@app.route('/produto/deletar/<int:id>')
@login_obrigatorio
def deletar_produto(id):
    """Excluir produto (soft delete)"""
    try:
        prod = Produto.query.get_or_404(id)
        
        # Verificar se há histórico vinculado
        if prod.cotacoes or prod.requisicoes:
            flash('Não é possível excluir produto com histórico!', 'error')
        else:
            db.session.delete(prod)
            db.session.commit()
            flash('Produto excluído com sucesso!', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir: {str(e)}', 'error')
    
    return redirect(url_for('produtos'))

# --- FORNECEDORES ---
@app.route('/fornecedores', methods=['GET', 'POST'])
@login_obrigatorio
def fornecedores():
    """Gestão de fornecedores - CORRIGIDO"""
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            
            if not nome:
                flash('Nome do fornecedor é obrigatório!', 'error')
                return redirect(url_for('fornecedores'))
            
            # Verificar se fornecedor já existe
            existente = Fornecedor.query.filter_by(nome=nome).first()
            if existente:
                flash(f'Fornecedor "{nome}" já existe!', 'error')
                return redirect(url_for('fornecedores'))
            
            # Criar novo fornecedor
            novo_fornecedor = Fornecedor(
                nome=nome
            )
            
            db.session.add(novo_fornecedor)
            db.session.commit()
            
            flash('Fornecedor cadastrado com sucesso!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar fornecedor: {str(e)}', 'error')
    
    # Listar fornecedores cadastrados
    fornecedores_cadastrados = Fornecedor.query.order_by(Fornecedor.nome).all()
    
    return render_template('fornecedores.html', fornecedores=fornecedores_cadastrados)

@app.route('/fornecedor/editar/<int:id>', methods=['GET', 'POST'])
@login_obrigatorio
def editar_fornecedor(id):
    """Editar fornecedor existente"""
    forn = Fornecedor.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            novo_nome = request.form.get('nome', '').strip()
            if not novo_nome:
                flash('Nome não pode ser vazio!', 'error')
                return redirect(url_for('editar_fornecedor', id=id))
            
            # Verificar se outro fornecedor já tem este nome
            existente = Fornecedor.query.filter(
                Fornecedor.nome == novo_nome, 
                Fornecedor.id != id
            ).first()
            
            if existente:
                flash('Já existe outro fornecedor com este nome!', 'error')
                return redirect(url_for('editar_fornecedor', id=id))
            
            forn.nome = novo_nome
            db.session.commit()
            flash('Fornecedor atualizado com sucesso!', 'success')
            return redirect(url_for('fornecedores'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar: {str(e)}', 'error')
    
    return render_template('editar_generico.html', tipo='Fornecedor', item=forn)

@app.route('/fornecedor/deletar/<int:id>')
@login_obrigatorio
def deletar_fornecedor(id):
    """Excluir fornecedor"""
    try:
        forn = Fornecedor.query.get_or_404(id)
        
        # Verificar se há histórico vinculado
        if forn.cotacoes:
            flash('Não é possível excluir fornecedor com histórico de cotações!', 'error')
        else:
            db.session.delete(forn)
            db.session.commit()
            flash('Fornecedor excluído com sucesso!', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir: {str(e)}', 'error')
    
    return redirect(url_for('fornecedores'))

# --- REQUISIÇÕES E COTAÇÕES ---
@app.route('/requisicoes', methods=['GET', 'POST'])
@login_obrigatorio
def requisicoes():
    """Preparação de cotações - CORRIGIDO"""
    # Obter TODOS os fornecedores do banco de dados
    fornecedores = Fornecedor.query.order_by(Fornecedor.nome).all()
    
    # Obter requisições pendentes
    requisicoes_pendentes = Requisicao.query.filter_by(status='Pendente').order_by(Requisicao.data_pedido.desc()).all()
    
    if request.method == 'POST':
        try:
            produto_id = request.form.get('produto_id')
            quantidade = request.form.get('quantidade', 1, type=int)
            fornecedores_ids = request.form.getlist('fornecedores_ids')
            
            # Validações
            if not produto_id:
                flash('Informe o código do produto!', 'error')
                return redirect(url_for('requisicoes'))
            
            produto = Produto.query.get(produto_id)
            if not produto:
                flash('Produto não encontrado!', 'error')
                return redirect(url_for('requisicoes'))
            
            # Se nenhum fornecedor selecionado, usa todos ativos
            if not fornecedores_ids:
                fornecedores_ids = [f.id for f in fornecedores]
                flash('Nenhum fornecedor selecionado. Todos os fornecedores serão incluídos.', 'warning')
            
            # Criar nova requisição
            nova_req = Requisicao(
                produto_id=produto_id,
                quantidade=quantidade
            )
            
            # Adicionar fornecedores selecionados
            for f_id in fornecedores_ids:
                forn = Fornecedor.query.get(f_id)
                if forn:
                    nova_req.fornecedores_selecionados.append(forn)
            
            db.session.add(nova_req)
            db.session.commit()
            
            flash(f'Item "{produto.nome}" adicionado com {len(fornecedores_ids)} fornecedor(es)!', 'success')
            return redirect(url_for('requisicoes'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar item: {str(e)}', 'error')
            return redirect(url_for('requisicoes'))
    
    # Se não houver fornecedores, mostrar mensagem
    if not fornecedores:
        flash('Cadastre fornecedores antes de criar cotações.', 'warning')
    
    # Passar para o template
    return render_template(
        'requisicoes.html',
        fornecedores=fornecedores,
        requisicoes=requisicoes_pendentes
    )

@app.route('/api/produto/<int:id>')
@login_obrigatorio
def api_produto_detalhes(id):
    """API para obter detalhes do produto"""
    produto = Produto.query.get(id)
    if produto:
        return jsonify({
            'id': produto.id,
            'nome': produto.nome,
            'existe': True
        })
    return jsonify({'existe': False, 'nome': ''})

@app.route('/api/verificar_codigo/<int:id>')
@login_obrigatorio
def api_verificar_codigo(id):
    """API para verificar se código já existe"""
    produto = Produto.query.get(id)
    return jsonify({'existe': produto is not None})

@app.route('/remover_requisicao/<int:id>')
@login_obrigatorio
def remover_requisicao(id):
    """Remover requisição pendente"""
    try:
        req = Requisicao.query.get_or_404(id)
        db.session.delete(req)
        db.session.commit()
        flash('Item removido da lista de cotação!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao remover: {str(e)}', 'error')
    
    return redirect(url_for('requisicoes'))

# Cotação Individual
@app.route('/realizar_cotacao/<int:req_id>', methods=['GET', 'POST'])
@login_obrigatorio
def realizar_cotacao(req_id):
    """Realizar cotação individual"""
    req = Requisicao.query.get_or_404(req_id)
    
    if request.method == 'POST':
        try:
            fornecedor_id = request.form.get('fornecedor_id')
            preco_str = request.form.get('preco', '0')
            
            if not fornecedor_id:
                flash('Selecione um fornecedor!', 'error')
                return redirect(url_for('realizar_cotacao', req_id=req_id))
            
            preco = parse_moeda(preco_str)
            if preco is None or preco <= 0:
                flash('Preço inválido!', 'error')
                return redirect(url_for('realizar_cotacao', req_id=req_id))
            
            # Criar cotação
            nova_cot = Cotacao(
                produto_id=req.produto_id,
                fornecedor_id=fornecedor_id,
                preco=preco,
                requisicao_origem_id=req.id
            )
            
            # Atualizar status da requisição
            req.status = 'Cotado'
            
            db.session.add(nova_cot)
            db.session.commit()
            
            flash('Cotação registrada com sucesso!', 'success')
            return redirect(url_for('requisicoes'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar cotação: {str(e)}', 'error')
    
    # GET: Exibir formulário
    fornecedores_lista = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    
    return render_template('fazer_cotacao.html', 
                         requisicao=req, 
                         fornecedores=fornecedores_lista)

# Mapa de Cotação (Lote)
@app.route('/mapa_cotacao', methods=['GET', 'POST'])
@login_obrigatorio
def mapa_cotacao():
    """Mapa de cotação inteligente"""
    pendentes = Requisicao.query.filter_by(status='Pendente').all()
    
    if not pendentes:
        flash('Não há itens pendentes para cotação!', 'warning')
        return redirect(url_for('requisicoes'))
    
    # Buscar todos os fornecedores ativos
    fornecedores = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    
    if request.method == 'POST':
        try:
            resultados = {}
            
            for req in pendentes:
                menor_preco = float('inf')
                vencedor_id = None
                vencedor_nome = None
                
                # Buscar preços apenas dos fornecedores selecionados
                fornecedores_para_cotar = req.fornecedores_selecionados or fornecedores
                
                for forn in fornecedores_para_cotar:
                    input_name = f"preco_{req.id}_{forn.id}"
                    valor_str = request.form.get(input_name, "").strip()
                    
                    if valor_str:
                        preco = parse_moeda(valor_str)
                        if preco is not None and preco > 0:
                            if preco < menor_preco:
                                menor_preco = preco
                                vencedor_id = forn.id
                                vencedor_nome = forn.nome
                
                # Se achou um vencedor, salva
                if vencedor_id:
                    nova_cotacao = Cotacao(
                        produto_id=req.produto_id,
                        fornecedor_id=vencedor_id,
                        preco=menor_preco,
                        requisicao_origem_id=req.id
                    )
                    req.status = 'Cotado'
                    db.session.add(nova_cotacao)
                    
                    if vencedor_id not in resultados:
                        resultados[vencedor_id] = {
                            'nome': vencedor_nome,
                            'itens': [],
                            'total': 0
                        }
                    
                    resultados[vencedor_id]['itens'].append({
                        'produto': req.produto.nome,
                        'produto_id': req.produto_id,
                        'preco': menor_preco,
                        'quantidade': req.quantidade,
                        'subtotal': menor_preco * req.quantidade
                    })
                    resultados[vencedor_id]['total'] += menor_preco * req.quantidade
                
                # Marcar como processado
                req.status = 'Processado'
            
            db.session.commit()
            
            # Preparar relatório detalhado
            relatorio = []
            for fid, dados in resultados.items():
                relatorio.append({
                    'fornecedor': dados['nome'],
                    'itens': dados['itens'],
                    'total': dados['total']
                })
            
            # Ordenar por total (maior para menor)
            relatorio.sort(key=lambda x: x['total'], reverse=True)
            
            return render_template('relatorio_vencedores.html', relatorio=relatorio)
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar: {str(e)}', 'error')
    
    return render_template('mapa_cotacao.html', 
                         pendentes=pendentes, 
                         fornecedores=fornecedores)

@app.route('/relatorio_vencedores')
@login_obrigatorio
def relatorio_vencedores_view():
    """Página de relatório de vencedores"""
    cotacoes = Cotacao.query.order_by(Cotacao.data_cotacao.desc()).all()
    
    # Agrupar por fornecedor
    fornecedores_vencedores = {}
    for cotacao in cotacoes:
        forn_nome = cotacao.fornecedor.nome
        if forn_nome not in fornecedores_vencedores:
            fornecedores_vencedores[forn_nome] = {
                'fornecedor': cotacao.fornecedor,
                'itens': [],
                'total': 0
            }
        fornecedores_vencedores[forn_nome]['itens'].append(cotacao)
        fornecedores_vencedores[forn_nome]['total'] += cotacao.preco
    
    relatorio = list(fornecedores_vencedores.values())
    relatorio.sort(key=lambda x: x['total'], reverse=True)
    
    return render_template('relatorio_vencedores.html', relatorio=relatorio)

@app.route('/exportar_relatorio_pdf')
@login_obrigatorio
def exportar_relatorio_pdf():
    """Exportar relatório de cotações em PDF"""
    cotacoes = Cotacao.query.order_by(Cotacao.data_cotacao.desc()).all()
    
    # Criar buffer para PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container de elementos
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilos customizados
    titulo_style = ParagraphStyle(
        'TituloCustom',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#e40c0c'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitulo_style = ParagraphStyle(
        'SubtituloCustom',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
        alignment=TA_CENTER
    )
    
    # Cabeçalho
    elements.append(Paragraph("TINDIANA LOGÍSTICA", titulo_style))
    elements.append(Paragraph("Relatório de Cotações por Fornecedor", subtitulo_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}", subtitulo_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Agrupar por fornecedor
    fornecedores_vencedores = {}
    for cotacao in cotacoes:
        forn_nome = cotacao.fornecedor.nome
        if forn_nome not in fornecedores_vencedores:
            fornecedores_vencedores[forn_nome] = {
                'fornecedor': cotacao.fornecedor,
                'itens': [],
                'total': 0
            }
        fornecedores_vencedores[forn_nome]['itens'].append(cotacao)
        fornecedores_vencedores[forn_nome]['total'] += cotacao.preco
    
    relatorio = sorted(fornecedores_vencedores.values(), key=lambda x: x['total'], reverse=True)
    
    # Gerar tabelas para cada fornecedor
    for idx, dados in enumerate(relatorio):
        if idx > 0:
            elements.append(PageBreak())
        
        # Nome do fornecedor
        forn_style = ParagraphStyle(
            'FornecedorStyle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#e40c0c'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        )
        
        elements.append(Paragraph(f"📦 {dados['fornecedor'].nome}", forn_style))
        
        # Tabela de itens
        table_data = [
            ['Cód.', 'Descrição', 'Preço Unit.', 'Qtd.', 'Subtotal']
        ]
        
        total_itens = 0
        for cot in dados['itens']:
            table_data.append([
                str(cot.produto.id),
                cot.produto.nome[:40],
                f"R$ {cot.preco:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                str(getattr(cot, 'requisicao_origem_id', '1')),
                f"R$ {cot.preco:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            ])
            total_itens += 1
        
        # Linha de total
        table_data.append(['', '', '', 'TOTAL:', f"R$ {dados['total']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')])
        
        # Criar tabela
        table = Table(table_data, colWidths=[0.8*inch, 2.5*inch, 1*inch, 0.7*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e40c0c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#fafafa')]),
            ('ALIGN', (2, 1), (-1, -2), 'RIGHT'),
            ('ALIGN', (3, 1), (-1, -2), 'CENTER'),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))
    
    # Rodapé
    elements.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Paragraph("Sistema Tindiana de Gestão de Cotações", footer_style))
    elements.append(Paragraph("Documento confidencial - Uso interno apenas", footer_style))
    
    # Gerar PDF
    doc.build(elements)
    buffer.seek(0)
    
    # Retornar como resposta
    from flask import send_file
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'relatorio_cotacoes_{datetime.now().strftime("%d_%m_%Y")}.pdf'
    )

@app.route('/historico_cotacoes')
@login_obrigatorio
def historico_cotacoes():
    """Histórico de cotações com filtros"""
    # Obter parâmetros de filtro
    filtro_fornecedor = request.args.get('fornecedor', '', type=str)
    filtro_data_inicio = request.args.get('data_inicio', '', type=str)
    filtro_data_fim = request.args.get('data_fim', '', type=str)
    filtro_produto = request.args.get('produto', '', type=str)
    
    # Começar com todas as cotações
    query = Cotacao.query
    
    # Aplicar filtros
    if filtro_fornecedor:
        try:
            query = query.join(Fornecedor).filter(Fornecedor.id == int(filtro_fornecedor))
        except:
            pass
    
    if filtro_produto:
        try:
            query = query.join(Produto).filter(Produto.id == int(filtro_produto))
        except:
            pass
    
    if filtro_data_inicio:
        try:
            data_inicio = datetime.strptime(filtro_data_inicio, '%Y-%m-%d').date()
            query = query.filter(Cotacao.data_cotacao >= data_inicio)
        except:
            pass
    
    if filtro_data_fim:
        try:
            data_fim = datetime.strptime(filtro_data_fim, '%Y-%m-%d').date()
            query = query.filter(Cotacao.data_cotacao <= data_fim)
        except:
            pass
    
    # Ordenar por data descendente
    cotacoes = query.order_by(Cotacao.data_cotacao.desc()).all()
    
    # Obter lista de fornecedores e produtos para os filtros
    fornecedores = Fornecedor.query.order_by(Fornecedor.nome).all()
    produtos = Produto.query.order_by(Produto.nome).all()
    
    # Calcular estatísticas dos resultados filtrados
    total_filtrado = sum(c.preco for c in cotacoes)
    media_filtrada = total_filtrado / len(cotacoes) if cotacoes else 0
    
    return render_template('historico.html', 
                         cotacoes=cotacoes,
                         fornecedores=fornecedores,
                         produtos=produtos,
                         filtro_fornecedor=filtro_fornecedor,
                         filtro_data_inicio=filtro_data_inicio,
                         filtro_data_fim=filtro_data_fim,
                         filtro_produto=filtro_produto,
                         total_filtrado=total_filtrado,
                         media_filtrada=media_filtrada)
@login_obrigatorio
def adicionar_item():
    """Página inicial para adicionar item para cotação"""
    if request.method == 'POST':
        produto_id = request.form.get('produto_id')
        quantidade = request.form.get('quantidade', 1, type=int)
        
        # VALIDAÇÃO
        if not produto_id:
            flash('Informe o código do produto!', 'error')
            return redirect(url_for('adicionar_item'))
        
        if quantidade <= 0:
            flash('Quantidade deve ser maior que zero!', 'error')
            return redirect(url_for('adicionar_item'))
        
        produto = Produto.query.get(produto_id)
        if not produto:
            flash('Produto não encontrado!', 'error')
            return redirect(url_for('adicionar_item'))
        
        # Redirecionar para seleção de fornecedores
        return redirect(url_for('selecionar_fornecedores', 
                              produto_id=produto_id, 
                              quantidade=quantidade))
    
    # GET: Mostrar formulário simples
    return render_template('adicionar_item.html')

@app.route('/deletar_cotacao_final/<int:id>')
@login_obrigatorio
def deletar_cotacao_final(id):
    """Excluir registro do histórico"""
    try:
        cotacao = Cotacao.query.get_or_404(id)
        
        # Verificar se há requisição vinculada
        if cotacao.requisicao_origem_id:
            req = Requisicao.query.get(cotacao.requisicao_origem_id)
            if req:
                req.status = 'Pendente'
        
        db.session.delete(cotacao)
        db.session.commit()
        flash('Registro de histórico removido!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir: {str(e)}', 'error')
    
    return redirect(url_for('historico_cotacoes'))

@app.route('/selecionar_fornecedores/<int:produto_id>', methods=['GET', 'POST'])
@login_obrigatorio
def selecionar_fornecedores(produto_id):
    """Seleção inteligente de fornecedores"""
    produto = Produto.query.get_or_404(produto_id)
    quantidade = request.args.get('quantidade', 1, type=int)
    
    if request.method == 'POST':
        try:
            fornecedores_ids = request.form.getlist('fornecedores_ids')
            
            if not fornecedores_ids:
                # Se nenhum fornecedor selecionado, usa todos
                fornecedores_ids = [f.id for f in Fornecedor.query.filter_by(ativo=True).all()]
            
            # Criar nova requisição
            nova_req = Requisicao(
                produto_id=produto_id,
                quantidade=quantidade
            )
            
            # Adicionar fornecedores selecionados
            for f_id in fornecedores_ids:
                forn = Fornecedor.query.get(f_id)
                if forn:
                    nova_req.fornecedores_selecionados.append(forn)
            
            db.session.add(nova_req)
            db.session.commit()
            
            flash(f'Item "{produto.nome}" adicionado com {len(fornecedores_ids)} fornecedor(es)!', 'success')
            return redirect(url_for('requisicoes'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {str(e)}', 'error')
    
    # GET: Mostrar fornecedores para seleção
    fornecedores = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    
    return render_template('selecionar_fornecedores.html', 
                         produto=produto, 
                         quantidade=quantidade,
                         fornecedores=fornecedores)

# --- ROTA 404 ---
@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template('404.html'), 404

# --- INICIALIZAÇÃO ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        inicializar_dados()
    
    # Adicionar informações de debug
    print("=" * 50)
    print("SISTEMA TINDIANA - LOGÍSTICA E COTAÇÕES")
    print("=" * 50)
    print("Banco de dados inicializado com sucesso!")
    print("Acesse: http://127.0.0.1:5000")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)