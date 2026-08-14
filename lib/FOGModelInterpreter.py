import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler
import shap

class FOGModelInterpreter:
    def __init__(self, model_paths):
        self.models = self.load_models(model_paths)
        self.scalers = self.initialize_scalers(model_paths)
        self.explainers = self.initialize_explainers(model_paths)
    
    def load_models(self, model_paths):
        return {task: joblib.load(path) for task, path in model_paths.items()}
    
    def initialize_scalers(self, model_paths):
        scalers = {}
        for task in model_paths.keys():
            scaler_path = model_paths[task].replace('.joblib', '_scaler.joblib')
            try:
                # Cargar el scaler guardado
                scalers[task] = joblib.load(scaler_path)
            except FileNotFoundError:
                print(f"No se encontró el scaler para {task}. Se usará StandardScaler por defecto.")
                scalers[task] = StandardScaler()

                # Si no está ajustado, asegúrate de hacerlo con datos de entrenamiento
                training_data = self.get_training_data(task)
                if training_data is not None:
                    scalers[task].fit(training_data)
                else:
                    raise ValueError(f"No hay datos de entrenamiento disponibles para ajustar el escalador de {task}.")
        return scalers
    
    def initialize_explainers(self, model_paths):
        explainers = {}
        for task, model in self.models.items():
            # Extraer el modelo desde el Pipeline si existe
            if hasattr(model, 'named_steps') and 'model' in model.named_steps:
                model_only = model.named_steps['model']
            else:
                model_only = model
            
            # Crear un explicador SHAP solo con el modelo, sin el Pipeline
            explainers[task] = shap.Explainer(model_only)
        
        return explainers
    
    def preprocess_data(self, input_data, task):
        # Verificar el tipo y forma de input_data antes de la transformación
        print(f"Tamaño de input_data antes de la transformación: {input_data.shape if isinstance(input_data, np.ndarray) else 'No es un ndarray'}")

        if not isinstance(input_data, np.ndarray):
            input_data = np.array(input_data).reshape(1, -1)
            
        # Verificar el tamaño después de la conversión
        print(f"Tamaño de input_data después de la conversión: {input_data.shape}")
        scaled_data = self.scalers[task].transform(input_data)
        
        # Preprocesamiento específico por tarea
        #if task == "unicast_download":
            #cpu_usage = scaled_data[:, 0]
            #scaled_data = np.column_stack((scaled_data, np.square(cpu_usage)))
        #elif task == "unicast_upload":
            #memory_usage = scaled_data[:, 0]
            #scaled_data = np.column_stack((scaled_data, np.square(cpu_usage)))
        #elif task == "multicast_download":
            #network_usage = scaled_data[:, 0]
            #scaled_data = np.column_stack((scaled_data, np.square(cpu_usage)))
        
        return scaled_data
    
    def predict(self, input_data, task):
        preprocessed_data = self.preprocess_data(input_data, task)
        return self.models[task].predict(preprocessed_data)
    
    def interpret_output(self, input_data, model_output, task):
        # Obtener el preprocesamiento de datos
        preprocessed_data = self.preprocess_data(input_data, task)
        
        # Obtener el explainer para la tarea
        explainer = self.explainers[task]
        
        # Calcular los valores SHAP
        shap_values = explainer(preprocessed_data)
        
        # Resumir la interpretación (por ejemplo, media de los valores SHAP)
        interpretation = {
            "prediction": model_output,
            "shap_values": shap_values.values.tolist(),
            "feature_importance": dict(zip(['feature1', 'feature2', 'feature3'], np.mean(np.abs(shap_values.values), axis=0)))
        }
        
        return interpretation
    
    def get_prediction(self, input_data, task):
        prediction = self.predict(input_data, task)
        interpretation = self.interpret_output(input_data, prediction, task)
        return interpretation
