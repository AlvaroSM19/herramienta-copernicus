# translator.py

"""Alias legibles para categorías y satélites."""

VARIABLES_ALIAS = {
    # GHRSST
    "sea_surface_temperature":                "Sea Surface Temperature",
    "analysed_sst":                           "Sea Surface Temperature",
    "sst":                                    "Sea Surface Temperature",
    "sea_ice_fraction":                       "Sea Ice Fraction",
    "ice_fraction":                           "Sea Ice Fraction",
    "wind_speed":                             "Wind Speed",
    "wind_speed_over_ocean":                  "Wind Speed",
   # Sentinel-3 SLSTR FRP (Fire Radiative Power)
    "FRP_MWIR": "Fire Radiative Power (MWIR)",
    "FRP_SWIR": "Fire Radiative Power (SWIR)",


    # Sentinel-5P
    "ozone_total_vertical_column":            "Ozone Total Column",
    "carbonmonoxide_total_column":            "Carbon Monoxide Column",
    "nitrogendioxide_tropospheric_column":    "Nitrogen Dioxide Column",
    "nitrogendioxide_stratospheric_column":   "Nitrogen Dioxide Stratospheric Column",
    "sulfurdioxide_total_vertical_column":    "Sulfur Dioxide Column",
    "formaldehyde_tropospheric_vertical_column": "Formaldehyde Tropospheric Column",
    "formaldehyde_tropospheric_vertical_column_precision": "Formaldehyde Precision",
    "methane_mixing_ratio_bias_corrected":    "Methane (CH4) Column",
    "aerosol_index_354_388":                  "Aerosol Index (354–388 nm)",
    "aerosol_index_340_380":                  "Aerosol Index (340–380 nm)",
    "aerosol_index_335_367":                  "Aerosol Index (335–367 nm)",
    "absorbing_aerosol_index":                "Aerosol Index",
    "aerosol_height":                         "Aerosol Layer Height",
    "cloud_fraction":                         "Cloud Fraction",
    "cloud_top_pressure":                     "Cloud Top Pressure",
    "cloud_optical_depth":                    "Cloud Optical Depth",
    "cloud_base_pressure":                    "Cloud Base Pressure",
    "cloud_albedo":                           "Cloud Albedo",

    # Sentinel-6
    "sea_level_anomaly":                      "Sea Level Anomaly",

    # AOD (Aerosol Optical Depth)
    "AOD_550":                               "AOD 550 nm",
    "AOD_550_Land":                          "AOD 550 nm (Land)",
    "AOD_550_Merged_OceanLand":              "AOD 550 nm (Merged)",
    "AOD_670":                               "AOD 670 nm",
    "AOD_865":                               "AOD 865 nm",
    "AOD_1600":                              "AOD 1600 nm",
    "AOD_2250":                              "AOD 2250 nm",

     # Viento y olas
    "wind_direction":            "Wind Direction",
    "significant_wave_height":   "Significant Wave Height",


    # Perfiles TROPOMI e IASI
    "ozone_number_density":      "Ozone Number Density",
    "ozone_partial_column":      "Ozone Partial Column",
    "air_temperature":           "Air Temperature (Profile)",
    "specific_humidity":         "Specific Humidity (Profile)",

    # VIIRS – incendios activos
    "fire_mask":                   "Active Fire Mask",
    "FP_power":                    "Fire Radiative Power",
    "power":                       "Fire Radiative Power",
    "FRP":                         "Fire Radiative Power",


    # SRAL (Altimetry Sentinel-3/6)
    "sea_surface_height":      "Sea Surface Height",
    "sea_level_anomaly":       "Sea Level Anomaly",
    "significant_wave_height": "Significant Wave Height",

    # SLSTR (AOD, FRP, SST)
    "AOD_550":           "Aerosol Optical Depth 550 nm",
    "aod550":            "Aerosol Optical Depth 550 nm",
    "FRP_MWIR":          "Fire Radiative Power (MWIR)",
    "FRP_SWIR":          "Fire Radiative Power (SWIR)",

    # ASCAT 
    "wind_speed":           "Wind Speed",
    "wind_direction":       "Wind Direction",

    # AVHRR
    "sea_surface_temperature": "Sea Surface Temperature",
    "analysed_sst":            "Sea Surface Temperature",
    "sst":                     "Sea Surface Temperature",

    # TROPOMI adicionales 
    "nitrogendioxide_total_column":   "Nitrogen Dioxide Column",
    "nitrogendioxide_tropospheric_column": "Nitrogen Dioxide Tropospheric Column",
    "nitrogendioxide_stratospheric_column": "Nitrogen Dioxide Stratospheric Column",
    "ozone_profile":                  "Ozone Profile",
    "aerosol_layer_height":           "Aerosol Layer Height",
    

}

SATELLITE_ALIAS = {
    "s3a":  "Sentinel-3A",
    "s3b":  "Sentinel-3B",
    "s5p":  "Sentinel-5P",
    "lpf-sl-2-aod": "Sentinel-5P",
    "lpf-sl-2-frp": "Sentinel-3",
    "s6a":  "Sentinel-6A",
    "s6":   "Sentinel-6",
    "npp": "NOAA",
    "metop": "Metop",
    "msg":  "MSG",
    "avhrr": "Metop (AVHRR)",
    "olci": "Sentinel-3 (OLCI)",
    "slstr": "Sentinel-3 (SLSTR)",
    "sral": "Sentinel-3 (SRAL)",
 # Si tienes otros satélites, añádelos aquí en minúsculas
}

CITY_COORDS = {
    "Gijon": (43.5368, -5.6615),
    "Madrid": (40.416775, -3.703790),
    "Barcelona": (41.390205, 2.154007),
    "Valencia": (39.466667, -0.375000),
    "Sevilla": (37.392529, -5.994072),
    "Galicia": (43.783333, -8.100000),
    "Lisboa": (38.722252, -9.139337),
    "Londres": (51.509865, -0.118092),
    "Berlín": (52.520008, 13.404954),
    "París": (48.864716, 2.349014),
    "Roma": (41.902782, 12.496366),
    "Nueva York": (40.730610, -73.935242),
    "Pekín": (39.916668, 116.383331),
    "Cancun": (21.161903, -86.851529),
    "Buenos Aires": (-34.603722, -58.381592),
    "Tokio": (35.652832, 139.839478),
    "Sydney": (-33.8610, 151.2128),
    "Etna (Sicilia)": (37.7510, 14.9934),
    "Personalizado": (None, None),
}



BBOX_PREDEFINIDAS = {
    "España peninsular": "-10.0, 35.0, 4.0, 45.0",
    "Asturias": "-7.3, 42.9, -4.5, 43.7",
    "Canarias": "-19.0, 27.5, -13.0, 29.5",
    "Madrid": "-4.0, 40.0, -3.0, 41.0",
    "Barcelona": "1.8, 41.2, 2.4, 41.7",
    "Gijon": "-5.8, 43.5, -5.6, 43.6",
    "Valencia": "-0.5, 39.3, -0.2, 39.6",
    "Sevilla": "-6.1, 37.3, -5.7, 37.5",
    "Galicia": "-9.3, 41.8, -7.0, 43.8",
    "Etna (Sicilia)": "14.90, 37.65, 15.15, 37.85",
    "Lisboa": "-9.3, 38.6, -9.0, 38.8",
    "Londres": "-0.5, 51.3, 0.3, 51.7",
    "Berlín": "13.0, 52.3, 13.7, 52.7",
    "París": "2.1, 48.7, 2.5, 49.0",
    "Roma": "12.3, 41.7, 12.7, 42.0",
    "Nueva York": "-74.3, 40.5, -73.7, 40.9",
    "Pekín": "115.0, 39.0, 117.0, 41.0",
    "Cancun": "-87.2, 21.0, -86.7, 21.3",
    "Buenos Aires": "-58.6, -34.7, -58.2, -34.5",
    "Tokio": "139.5, 35.5, 140.0, 35.9",
    "Sydney": "150.9, -34.1, 151.3, -33.7",
    "Europa Occidental": "-11.0, 35.0, 20.0, 60.0",
    "Personalizada": ""
}

colecciones = {
    "SST Sentinel-3 SLSTR": "EO:EUM:DAT:0412",
    "Aerosol Optical Depth Sentinel-3": "EO:EUM:DAT:0416",
    "TROPOMI NO2 Sentinel-5P": "EO:EUM:DAT:0076",
    "TROPOMI Aerosol Index Sentinel-5P": "EO:EUM:DAT:0072",
    "TROPOMI Cloud Fraction Sentinel-5P": "EO:EUM:DAT:0074",
    "TROPOMI CO Sentinel-5P": "EO:EUM:DAT:0073",
    "TROPOMI O3 Sentinel-5P": "EO:EUM:DAT:0077",
    "TROPOMI SO2 Sentinel-5P": "EO:EUM:DAT:0078",
    "TROPOMI HCHO Sentinel-5P": "EO:EUM:DAT:0075",
    "SLSTR Fire Radiative Power Sentinel-3": "EO:EUM:DAT:0417",
    "SST Metop AVHRR GHRSST": "EO:EUM:DAT:METOP:GLB-SST-NC",
    "ASCAT Coastal Winds 12.5 km Metop": "EO:EUM:DAT:METOP:OSI-104",
    "ASCAT Winds 25 km Metop": "EO:EUM:DAT:METOP:OSI-150-A",
    "Aerosol Layer Height Sentinel-5P": "EO:EUM:DAT:0103",
    "Ozone Profile Sentinel-5P": "EO:EUM:DAT:0602",
    "SRAL Altimetry Level 2 Global Sentinel-3": "EO:EUM:DAT:0415",
    "SLSTR Aerosol Optical Depth Sentinel-3": "EO:EUM:DAT:0416",
    "SLSTR Level 1B Radiances Sentinel-3": "EO:EUM:DAT:0411",
    "Poseidon-4 Level 2P Wind/Wave Sentinel-6": "EO:EUM:DAT:0142",
    "Poseidon-4 Level 3 Wind/Wave Sentinel-6": "EO:EUM:DAT:0143",
    "Poseidon-4 Altimetry Level 2 High Resolution Sentinel-6": "EO:EUM:DAT:0855",
    "TROPOMI Aerosol Layer Height Sentinel-5P": "EO:EUM:DAT:0103",
    "TROPOMI Ozone Profile Sentinel-5P": "EO:EUM:DAT:0602",
}

consumer_key = "3FQ9yz0gX3hdTaF8dQQOuQBnNIwa"
consumer_secret = "vKomi9Y3xmN9ixnbVNSQvTQoVz0a"