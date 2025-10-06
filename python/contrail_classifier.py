# Load pickle file from disk
import pickle
import sklearn
class ContrailClassifier:
    def __init__(self, model_path='python/models/contrails_lr_clip_vitb_patch16.pkl'):
        with open(model_path, 'rb') as f:
            self.model = pickle.load(f)
    
    def predict(self, embedding):
        """
        Predict the probability of contrail presence given an image embedding.

        Args:
            embedding (list or np.array): The image embedding vector.

        Returns:
            float: Probability of contrail presence (between 0 and 1).
        """
        # Check if embedding is of correct shape
        if len(embedding) != self.model.n_features_in_:
            raise ValueError(f"Expected embedding of length {self.model.n_features_in_}, got {len(embedding)}")
        prob = self.model.predict_proba([embedding])[0][1]  # Probability of the positive class
        return prob