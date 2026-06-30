# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime
from typing import List, Dict
import io


class ExportManager:
    """Gestion des exports de données"""

    @staticmethod
    def export_to_excel(data: List[Dict], filename: str = None) -> bytes:
        """
        Exporte les données vers Excel avec formatage
        Retourne les données en bytes pour téléchargement Streamlit
        """
        if not filename:
            filename = f"linkedin_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        df = pd.DataFrame(data)

        # Créer un buffer en mémoire
        output = io.BytesIO()

        # Créer le writer Excel avec xlsxwriter
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Profils', index=False)

            # Accéder au workbook et worksheet pour le formatage
            workbook = writer.book
            worksheet = writer.sheets['Profils']

            # Formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })

            url_format = workbook.add_format({
                'font_color': 'blue',
                'underline': True
            })

            # Formater l'en-tête
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Ajuster les largeurs de colonnes
            for i, col in enumerate(df.columns):
                if col == 'URL du profil' or col == 'url':
                    worksheet.set_column(i, i, 50, url_format)
                elif col == 'Nom' or col == 'nom':
                    worksheet.set_column(i, i, 25)
                elif col == 'Poste' or col == 'poste':
                    worksheet.set_column(i, i, 30)
                elif col == 'Entreprise' or col == 'entreprise':
                    worksheet.set_column(i, i, 25)
                elif col == 'Resume' or col == 'resume':
                    worksheet.set_column(i, i, 40)
                else:
                    worksheet.set_column(i, i, 15)

            # Figer la première ligne
            worksheet.freeze_panes(1, 0)

        output.seek(0)
        return output.getvalue()

    @staticmethod
    def export_to_csv(data: List[Dict], filename: str = None) -> str:
        """Exporte les données vers CSV"""
        if not filename:
            filename = f"linkedin_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        df = pd.DataFrame(data)
        return df.to_csv(index=False)

    @staticmethod
    def prepare_stats_for_export(stats: Dict) -> pd.DataFrame:
        """Prépare les statistiques pour l'export"""
        data = []

        data.append({"Métrique": "Total profils", "Valeur": stats.get('total_profils', 0)})
        data.append({"Métrique": "Total invitations", "Valeur": stats.get('total_invitations', 0)})
        data.append({"Métrique": "Invitations aujourd'hui", "Valeur": stats.get('invitations_aujourdhui', 0)})

        if 'derniere_recherche' in stats and stats['derniere_recherche']:
            dr = stats['derniere_recherche']
            data.append({"Métrique": "Dernière recherche - Keyword", "Valeur": dr.get('keyword', 'N/A')})
            data.append({"Métrique": "Dernière recherche - Date", "Valeur": dr.get('date', 'N/A')})
            data.append({"Métrique": "Dernière recherche - Profils", "Valeur": dr.get('nb_profils', 0)})

        return pd.DataFrame(data)
