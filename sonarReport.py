import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime

class Credentials:
    def __init__(self):
        json_file_path = ".pipelines/variables/appsettings.json"
        try:
            with open(json_file_path, "r") as json_file:
                data = json.load(json_file)
            self.SONARQUBE_TOKEN = data.get("SONARQUBE_TOKEN")
            self.PROJECT_IDS = data.get("PROJECT_IDS")
            self.SONARQUBE_URL = data.get("SONARQUBE_URL")
            self.SLACK_WEBHOOK_URL = data.get("SLACK_WEBHOOK_URL")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"Erro ao carregar as credenciais: {e}")

    def get_project_metrics(self, project_id):
        url = f"{self.SONARQUBE_URL}/api/measures/component"
        parametros = {
            "component": project_id,
            "metricKeys": "bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density,alert_status,quality_gate_details"
        }
        headers = {
            "Authorization": f"Bearer {self.SONARQUBE_TOKEN}"
        }
        response = requests.get(url, params=parametros, headers=headers)

        if response.status_code != 200:
            raise ValueError(
                f"Falha ao obter métricas para o projeto {project_id}. Código de status: {response.status_code}")

        data = response.json()

        metrics = {}
        for measure in data["component"]["measures"]:
            metric_name = measure["metric"]
            metric_value = measure["value"]
            metrics[metric_name] = metric_value

        # Verifica se o status do Quality Gate está presente na resposta
        quality_gate_status = None
        if "quality_gate_details" in data["component"]:
            quality_gate_status = data["component"]["quality_gate_details"]["conditions"][0]["status"]
        metrics['quality_gate'] = quality_gate_status

        return metrics

    def extract_metrics_from_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')

        all_classes = [element['class'] for element in soup.find_all(class_=True)]

        bugs = int(soup.find('span', {'class': 'bugs'}).text) if soup.find('span', {'class': 'bugs'}) else 0
        vulnerabilities = int(soup.find('span', {'class': 'vulnerabilities'}).text) if soup.find('span', {
            'class': 'vulnerabilities'}) else 0
        code_smells = int(soup.find('span', {'class': 'code-smells'}).text) if soup.find('span', {
            'class': 'code-smells'}) else 0

        metrics = {
            'bugs': bugs,
            'vulnerabilities': vulnerabilities,
            'code_smells': code_smells,
        }

        return metrics

    def get_coverage(self, project_id):
        url = f"{self.SONARQUBE_URL}/api/measures/component"
        parametros = {
            "component": project_id,
            "metricKeys": "coverage"
        }
        headers = {
            "Authorization": f"Bearer {self.SONARQUBE_TOKEN}"
        }
        response = requests.get(url, params=parametros, headers=headers)

        if response.status_code != 200:
            raise ValueError(
                f"Falha ao obter cobertura para o projeto {project_id}. Código de status: {response.status_code}")

        data = response.json()

        if len(data['component']['measures']) == 0:
            return "Not Applicable"
        else:
            coverage = float(data['component']['measures'][0]['value'])
            return coverage

    def generate_slack_message(self, metrics):
        blocks = []

        intro_text = ":bees-one: :sonarcloud: Sonarqube Report - "
        current_date = datetime.now().strftime("%m-%d-%Y :sonarcloud: :bees-one:")
        intro_text += current_date

        intro_block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": intro_text
            }
        }
        blocks.append(intro_block)

        for project_id, project_metrics in metrics.items():

            # Adicionando o nome do projeto como título
            project_link = f"https://sonarcloud.io/project/overview?id={project_id}"
            formatted_project_link = f"<{project_link}|{project_id}>"
            title_block = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{formatted_project_link}*"
                }
            }
            blocks.append(title_block)

            # Adicionando métricas
            bugs = project_metrics.get('bugs', 0)
            vulnerabilities = project_metrics.get('vulnerabilities', 0)
            code_smells = project_metrics.get('code_smells', 0)
            coverage = project_metrics.get('coverage', 0)
            quality_gate = project_metrics.get("quality_gate", None)
            metrics_block_text = (f"Coverage: {coverage}%\n"
                                  f"Bugs: {bugs}\n"
                                  f"Vulnerabilities: {vulnerabilities}\n"
                                  f"Code Smells: {code_smells}\n")

            if quality_gate is not None:
                quality_gate_status = ':check_green: Passed' if quality_gate == 'OK' else ':x: Failed'
                metrics_block_text += f"{quality_gate_status}\n"
            metrics_block = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": metrics_block_text
                }
            }
            blocks.append(metrics_block)


            # Adicionando separador
            blocks.append({"type": "divider"})

        slack_data = {"blocks": blocks}
        return json.dumps(slack_data)


    def obter_status_quality_gate(self, project_key):
        url = f"{self.SONARQUBE_URL}/api/qualitygates/project_status"
        parametros = {
            "projectKey": project_key
        }
        headers = {
            "Authorization": f"Bearer {self.SONARQUBE_TOKEN}"
        }
        response = requests.get(url, params=parametros, headers=headers)

        if response.status_code != 200:
            raise ValueError(
                f"Falha ao obter o status do Quality Gate para o projeto {project_key}. Código de status: {response.status_code}")

        return response.json()['projectStatus']['status']

    def send_slack_message(self, message):
        headers = {
            'Content-Type': 'application/json'
        }

        # Dados corrigidos para enviar a mensagem ao Slack
        data = {
            "text": "Métricas dos projetos do SonarQube:",
            "blocks": json.loads(message)["blocks"]
        }

        response = requests.post(self.SLACK_WEBHOOK_URL, headers=headers, json=data)

        if response.status_code != 200:
            raise ValueError(
                f"Erro ao enviar mensagem para o Slack. Código de status: {response.status_code}")



def main():
    credentials = Credentials()

    projects_metrics = {}
    for project_id in credentials.PROJECT_IDS:
        # Obtendo métricas de bugs, vulnerabilidades, code smells e cobertura
        metrics = credentials.get_project_metrics(project_id)
        coverage = credentials.get_coverage(project_id)
        metrics['coverage'] = coverage
        projects_metrics[project_id] = metrics

        # Obtendo status do Quality Gate
        status_quality_gate = credentials.obter_status_quality_gate(project_id)
        projects_metrics[project_id]['quality_gate'] = status_quality_gate

    # Gerando mensagem para o Slack
    message = credentials.generate_slack_message(projects_metrics)

    # Enviando mensagem para o Slack
    credentials.send_slack_message(message)


if __name__ == "__main__":
    main()