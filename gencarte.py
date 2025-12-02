from staticmap import StaticMap, CircleMarker
from PIL import Image
import io

def generate_map_image(
    img_width=800,
    img_height=534,
    center_lat=48.8504,
    center_lon=2.2181,
    zoom=13
):
    """
    Génère une image de carte centrée sur les coordonnées spécifiées.
    Retourne directement une image PIL (pas enregistrée sur disque).
    """
    
    # Créer la carte
    m = StaticMap(img_width, img_height,
                  url_template='https://tile.openstreetmap.org/{z}/{x}/{y}.png')

    # Ajouter un marqueur invisible pour centrer
    marker = CircleMarker((center_lon, center_lat), "#00000000", 0)
    m.add_marker(marker)

    # Rendu de l'image sous forme d'image PIL
    image = m.render(zoom=zoom)

    return image