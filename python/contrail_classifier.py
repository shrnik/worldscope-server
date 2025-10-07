# Load pickle file from disk
import pickle
import torch
import torch
import torch.nn as nn
import torch.optim as optim

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
    

class BinaryClassifier(nn.Module):
    def __init__(self, input_dim=512, hidden_dim=256):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        return self.classifier(x)

class ContrailClassifierNN:
    def __init__(self, model_path='python/models/simple_nn_contrails.pth'):
        # Load the neural network model from the specified path
        self.model = BinaryClassifier(768, 256)  # Assuming input dimension is 768
        self.model.load_state_dict(torch.load(model_path))
        self.model.eval()  # Set the model to evaluation mode

    def predict(self, embedding):
        """
        Predict the probability of contrail presence given an image embedding.

        Args:
            embedding (list or np.array): The image embedding vector.

        Returns:
            float: Probability of contrail presence (between 0 and 1).
        """
        # Check if embedding is of correct shape
        if len(embedding) != self.model.input_size:
            raise ValueError(f"Expected embedding of length {self.model.input_size}, got {len(embedding)}")
        with torch.no_grad():
            embedding_tensor = torch.tensor(embedding).float()
            prob = self.model(embedding_tensor).item()
        return prob


