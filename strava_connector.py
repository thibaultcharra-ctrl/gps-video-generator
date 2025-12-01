# strava_connector.py
"""
Module pour se connecter à l'API Strava et télécharger les activités GPS
"""
import os
import requests
import time
import json
from datetime import datetime, timedelta

class StravaConnector:
    """Gère la connexion et le téléchargement des activités Strava"""
    
    def __init__(self, client_id=None, client_secret=None, refresh_token=None):
        """
        Initialise le connecteur Strava
        
        Args:
            client_id: ID client Strava API
            client_secret: Secret client Strava API
            refresh_token: Token de refresh pour l'authentification
        """
        self.client_id = client_id or os.environ.get('STRAVA_CLIENT_ID')
        self.client_secret = client_secret or os.environ.get('STRAVA_CLIENT_SECRET')
        self.refresh_token = refresh_token or os.environ.get('STRAVA_REFRESH_TOKEN')
        
        self.access_token = None
        self.token_expires_at = 0
        
        self.base_url = "https://www.strava.com/api/v3"
    
    def get_access_token(self):
        """
        Obtient un nouveau access token à partir du refresh token
        
        Returns:
            str: Access token valide
        """
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        print("🔄 Rafraîchissement du token Strava...")
        
        url = "https://www.strava.com/oauth/token"
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(url, data=payload)
        
        if response.status_code != 200:
            raise Exception(f"Erreur lors du rafraîchissement du token: {response.text}")
        
        data = response.json()
        self.access_token = data['access_token']
        self.token_expires_at = data['expires_at']
        
        print("✅ Token obtenu avec succès")
        return self.access_token
    
    def get_athlete_info(self):
        """
        Récupère les informations de l'athlète connecté
        
        Returns:
            dict: Informations de l'athlète
        """
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(f"{self.base_url}/athlete", headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Erreur lors de la récupération des infos athlète: {response.text}")
        
        return response.json()
    
    def get_activities(self, after=None, before=None, page=1, per_page=30):
        """
        Récupère la liste des activités
        
        Args:
            after: Timestamp Unix - activités après cette date
            before: Timestamp Unix - activités avant cette date
            page: Numéro de page
            per_page: Nombre d'activités par page (max 200)
        
        Returns:
            list: Liste des activités
        """
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        params = {
            'page': page,
            'per_page': per_page
        }
        
        if after:
            params['after'] = int(after)
        if before:
            params['before'] = int(before)
        
        response = requests.get(
            f"{self.base_url}/athlete/activities",
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            raise Exception(f"Erreur lors de la récupération des activités: {response.text}")
        
        return response.json()
    
    def get_all_activities(self, after=None, before=None, activity_types=None):
        """
        Récupère toutes les activités (gère la pagination automatiquement)
        
        Args:
            after: datetime - activités après cette date
            before: datetime - activités avant cette date
            activity_types: list - types d'activités à filtrer (ex: ['Run', 'Ride'])
        
        Returns:
            list: Liste de toutes les activités
        """
        all_activities = []
        page = 1
        
        # Convertir datetime en timestamp Unix
        after_ts = int(after.timestamp()) if after else None
        before_ts = int(before.timestamp()) if before else None
        
        print(f"📥 Récupération des activités Strava...")
        
        while True:
            activities = self.get_activities(
                after=after_ts,
                before=before_ts,
                page=page,
                per_page=200
            )
            
            if not activities:
                break
            
            # Filtrer par type d'activité si spécifié
            if activity_types:
                activities = [a for a in activities if a.get('type') in activity_types]
            
            all_activities.extend(activities)
            print(f"   Page {page}: {len(activities)} activités récupérées")
            
            page += 1
            
            # Limite de sécurité
            if page > 100:
                print("⚠️  Limite de 100 pages atteinte")
                break
        
        print(f"✅ Total: {len(all_activities)} activités récupérées")
        return all_activities
    
    def download_activity_gpx(self, activity_id, output_folder, filename=None):
        """
        Télécharge le fichier GPX d'une activité
        
        Args:
            activity_id: ID de l'activité
            output_folder: Dossier de destination
            filename: Nom du fichier (optionnel)
        
        Returns:
            str: Chemin du fichier téléchargé ou None
        """
        token = self.get_access_token()
        headers = {'Authorization': f'Bearer {token}'}
        
        url = f"{self.base_url}/activities/{activity_id}/streams"
        params = {
            'keys': 'latlng,time,altitude',
            'key_by_type': 'true'
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"⚠️  Impossible de télécharger l'activité {activity_id}: {response.status_code}")
            return None
        
        data = response.json()
        
        # Vérifier si on a des données GPS
        if 'latlng' not in data or not data['latlng'].get('data'):
            print(f"⚠️  Pas de données GPS pour l'activité {activity_id}")
            return None
        
        # Créer le fichier GPX
        os.makedirs(output_folder, exist_ok=True)
        
        if not filename:
            filename = f"strava_{activity_id}.gpx"
        
        filepath = os.path.join(output_folder, filename)
        
        # Générer le contenu GPX
        gpx_content = self._create_gpx_from_streams(data, activity_id)
        
        with open(filepath, 'w') as f:
            f.write(gpx_content)
        
        return filepath
    
    def _create_gpx_from_streams(self, streams, activity_id):
        """
        Crée un fichier GPX à partir des données de streams
        
        Args:
            streams: Données des streams Strava
            activity_id: ID de l'activité
        
        Returns:
            str: Contenu du fichier GPX
        """
        latlng = streams['latlng']['data']
        times = streams.get('time', {}).get('data', [])
        altitudes = streams.get('altitude', {}).get('data', [])
        
        # En-tête GPX
        gpx = ['<?xml version="1.0" encoding="UTF-8"?>']
        gpx.append('<gpx version="1.1" creator="Strava GPS Video Generator">')
        gpx.append(f'  <metadata>')
        gpx.append(f'    <name>Strava Activity {activity_id}</name>')
        gpx.append(f'  </metadata>')
        gpx.append('  <trk>')
        gpx.append(f'    <name>Activity {activity_id}</name>')
        gpx.append('    <trkseg>')
        
        # Points GPS
        base_time = datetime.now()
        for i, (lat, lon) in enumerate(latlng):
            gpx.append('      <trkpt lat="{}" lon="{}">'.format(lat, lon))
            
            # Altitude si disponible
            if i < len(altitudes):
                gpx.append(f'        <ele>{altitudes[i]}</ele>')
            
            # Temps si disponible
            if i < len(times):
                time_offset = timedelta(seconds=times[i])
                timestamp = (base_time + time_offset).isoformat()
                gpx.append(f'        <time>{timestamp}Z</time>')
            
            gpx.append('      </trkpt>')
        
        # Fermeture GPX
        gpx.append('    </trkseg>')
        gpx.append('  </trk>')
        gpx.append('</gpx>')
        
        return '\n'.join(gpx)
    
    def download_activities(self, output_folder, after=None, before=None, 
                           activity_types=None, max_activities=None):
        """
        Télécharge plusieurs activités
        
        Args:
            output_folder: Dossier de destination
            after: datetime - activités après cette date
            before: datetime - activités avant cette date
            activity_types: list - types d'activités (ex: ['Run', 'Ride'])
            max_activities: int - nombre maximum d'activités à télécharger
        
        Returns:
            list: Liste des fichiers téléchargés
        """
        activities = self.get_all_activities(
            after=after,
            before=before,
            activity_types=activity_types
        )
        
        if max_activities:
            activities = activities[:max_activities]
        
        print(f"\n📥 Téléchargement de {len(activities)} activités...")
        
        downloaded_files = []
        
        for i, activity in enumerate(activities, 1):
            activity_id = activity['id']
            activity_name = activity.get('name', 'Unnamed')
            activity_date = activity.get('start_date', '')
            
            print(f"   [{i}/{len(activities)}] {activity_name} ({activity_date[:10]})")
            
            filepath = self.download_activity_gpx(
                activity_id,
                output_folder,
                filename=f"strava_{activity_id}.gpx"
            )
            
            if filepath:
                downloaded_files.append(filepath)
            
            # Respect des limites de l'API (100 requêtes / 15 min)
            time.sleep(0.2)
        
        print(f"\n✅ {len(downloaded_files)} fichiers téléchargés avec succès!")
        return downloaded_files


def get_strava_auth_url(client_id, redirect_uri="http://localhost:8501"):
    """
    Génère l'URL d'authentification Strava
    
    Args:
        client_id: ID client Strava
        redirect_uri: URI de redirection
    
    Returns:
        str: URL d'authentification
    """
    scope = "activity:read_all"
    return (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
    )


def exchange_code_for_token(client_id, client_secret, code):
    """
    Échange le code d'autorisation contre un token
    
    Args:
        client_id: ID client Strava
        client_secret: Secret client Strava
        code: Code d'autorisation reçu après authentification
    
    Returns:
        dict: Tokens d'accès et de refresh
    """
    url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code'
    }
    
    response = requests.post(url, data=payload)
    
    if response.status_code != 200:
        raise Exception(f"Erreur lors de l'échange du code: {response.text}")
    
    return response.json()


# Exemple d'utilisation
if __name__ == "__main__":
    # Configuration
    connector = StravaConnector(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        refresh_token="YOUR_REFRESH_TOKEN"
    )
    
    # Récupérer les infos de l'athlète
    athlete = connector.get_athlete_info()
    print(f"Connecté en tant que: {athlete['firstname']} {athlete['lastname']}")
    
    # Télécharger les activités des 30 derniers jours
    after_date = datetime.now() - timedelta(days=30)
    
    files = connector.download_activities(
        output_folder="strava_activities",
        after=after_date,
        activity_types=['Run', 'Ride'],
        max_activities=50
    )
    
    print(f"\nFichiers téléchargés: {len(files)}")