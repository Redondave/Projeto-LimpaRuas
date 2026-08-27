import csv
import os

# dicionario para traduzir o código da rodovia para o seu local (início - fim)
road_translation = {}

# flag para sair do programa
quit_requested = 0

# função para limpar a tela
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# define a flag de sair do programa
def quit():
    global quit_requested
    quit_requested = 1
    return 

# preenche a tabela de mapeamento do código da rodovia para o local
def populate():
    global road_translation
    with open("Roads.csv", encoding='utf-8-sig') as map:
        reader = csv.DictReader(map)
        for line in reader:
            road_translation[line['CÓDIGO-DO-TRECHO']] = f"{line['TRECHO-INÍCIO']} até {line['TRECHO-FINAL']}"
    

def parser(file, cat):
    # Abrir o .csv e filtrar por nome da rodovia o total de veículos dentro dos dias de dada semana
    # formatar como um dicionário de valores e retornar para a função 'assemble'
    result = {}
    with open(file, encoding='utf-8-sig') as info:
        reader = csv.DictReader(info)
        for line in reader:
            # pega apenas os dados relevantes para a pesquisa (moto, onibus, total...)
            if (line['porte'].lower() == cat.lower()):
                if line['trecho'] not in result:
                    result[line['trecho']] = []
                result[line['trecho']].append(int(line['fluxo']))
    return result


def assemble(dict):
    # TODO - pegar o dicionário gerado e imprimir informações mais relevantes (máx, min e média...), e retornar um .csv agregado
    totals = {}
    global road_translation
    for r in dict:
        totals[r] = 0
        for qtd in dict[r]:
            totals[r] += qtd
            
    totals_sorted = sorted(totals.items(), key = lambda item : item[1], reverse = True)
    return totals_sorted

def calculate(road):
    # TODO - Calcular a Vmédia e o N para as rodovias de interesse a partir dos dados agregados de 'parser' ou 'assemble' 
    # e das informações das rodovias do DETRAN
    clear_screen()
    global road_translation
    print(f"Analisando rodovia: {road} : {road_translation[road]}\n")

    # captura a opção desejada e valida o input
    option = int(input("Selecione operação desejada:\n1-Ver informações gerais\n2-Calcular N\n3-Voltar\n"))
    if option not in range(1,4):
        input("Opção inválida!")
        calculate(road)

    if option == 1:

        # imprime todas as informações da rodovia
        with open("Roads.csv", encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            found = 0
            headers = next(reader)
            for line in reader:
                if line['CÓDIGO-DO-TRECHO'] == road:
                    for col in headers:
                        print(f"{col} : {line[col]}")
                    found = 1
                    break

            if not found:
                print("Rodovia não localizada!")

    elif option == 2:
        # TODO - precisa desenvolver função de cálculo do N
        print("Função ainda não implementada :P")
    else:
        interface()

    return

    return

def interface():
    global road_translation
    clear_screen()

    # captura a operação desejada pelo usuário e checa validade do input
    option = int(input("Informe a operação desejada:\n1-Visualizar dados viários\n2-Ver mapa de códigos e nomes de rodovias\n3-Operações sobre uma rodovia\n4-Sair\n"))

    if option == 1:
        category = -1
        while category not in range(1,5):
            clear_screen()
            # captura a categoria de veículos desejada e checa validade
            category = int(input("Informe a categoria de veículos:\n1-Moto\n2-Carro\n3-Onibus\n4-Total\n5-Voltar\n"))
            if category == 5:
                interface()
            cat_type = "moto" if category == 1 else "carro" if category == 2 else "onibus" if category == 3 else "total" if category == 4 else -1
    
        print("Analisando a base de dados...")

        # extrai apenas os dados relevantes para a categoria, e devolve um dicionário ordenado e traduzido
        roads_dict = parser("Flow.csv", cat_type)
        totals_sorted = assemble(roads_dict)

        print("Total por rodovias: ")
        for x in totals_sorted:
            print(f"Total: {x[1]}, Rua: {road_translation[x[0]] if x[0] in road_translation else "Rodovia não identificada"}")
    
    elif option == 2:
        # apenas imprime a tabela de mapeamento das rodovias e seus nomes
        road_translation
        for code in road_translation:
            print(f"Código: {code}, Nome: {road_translation[code]}")
    
    elif option == 3:
        # chama a função de cálculo para uma das rodovias
        road = input("Digite o código da rodovia no formato (XXXAAAXXXX):\n")
        calculate(road)

    elif option == 4:
        quit()
        return

    else:
        print("Opção inválida! Tente uma das disponíveis")
    input("Pressione [ENTER] para continuar")

def main():
    # popula a tabela de mapeamento e chama a interação com o usuário até o 'quit'
    print("Carregando dados...")
    populate()

    while not quit_requested:
        interface()

    return

main()