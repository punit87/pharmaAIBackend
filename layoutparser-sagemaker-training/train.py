import os
import logging
import boto3
import torch
import json
from detectron2.config import get_cfg
from detectron2.engine import DefaultTrainer
from detectron2.data import DatasetCatalog, MetadataCatalog
from detectron2.data.datasets import register_coco_instances
from detectron2.model_zoo import model_zoo
from layoutparser.models import Detectron2LayoutModel
from pathlib import Path
import time
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/ml/output/train.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants from environment variables
S3_BUCKET = os.environ['ENV_TRAIN_LP_S3_BUCKET']
S3_PREFIX = os.environ['ENV_TRAIN_LP_S3_PREFIX']
CHECKPOINT_DIR = Path(os.environ['ENV_TRAIN_LP_CHECKPOINT_DIR'])
OUTPUT_DIR = Path(os.environ['ENV_TRAIN_LP_OUTPUT_DIR'])
PRETRAINED_DIR = Path(os.environ['ENV_TRAIN_LP_PRETRAINED_DIR'])
DEVICE = os.environ['ENV_TRAIN_LP_DEVICE'] if torch.cuda.is_available() else 'cpu'
LABEL_MAP = json.loads(os.environ['ENV_TRAIN_LP_LABEL_MAP'])

def load_hyperparameters():
    """Load hyperparameters from SageMaker's hyperparameters.json."""
    hyperparam_path = '/opt/ml/input/config/hyperparameters.json'
    try:
        with open(hyperparam_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Hyperparameters file not found, using defaults")
        return {}
    except Exception as e:
        logger.error(f"Failed to load hyperparameters: {e}")
        return {}

def print_training_steps(hyperparameters):
    """Print all steps the script will perform before execution."""
    num_workers = hyperparameters.get('num_workers', 2)
    ims_per_batch = hyperparameters.get('ims_per_batch', 2)
    base_lr = hyperparameters.get('base_lr', 0.00025)
    max_iter = hyperparameters.get('max_iter', 300)
    checkpoint_period = hyperparameters.get('checkpoint_period', 100)
    roi_batch_size = hyperparameters.get('roi_batch_size', 128)
    
    print("The script will perform the following steps:")
    print(f"1. Download training data from S3 path: s3://{S3_BUCKET}/{S3_PREFIX}data/ to local directory: /opt/ml/input/data/training")
    print("2. Verify the existence of a JSON file and image directory in /opt/ml/input/data/training")
    print("3. Register the dataset 'custom_layout_dataset' using the JSON file and image directory")
    print(f"4. Download pretrained model weights from S3 path: s3://{S3_BUCKET}/{S3_PREFIX}models/model_final.pth to {PRETRAINED_DIR}/model_final.pth")
    print(f"5. Configure the layout-parser model, using pretrained weights from {PRETRAINED_DIR}/model_final.pth if available, or default weights from Detectron2 model zoo")
    print(f"6. Check for and download existing checkpoints from S3 path: s3://{S3_BUCKET}/{S3_PREFIX}checkpoints/ to {CHECKPOINT_DIR}")
    print("7. Resume training from a checkpoint if available, or start training from scratch")
    print(f"8. Train the model for {max_iter} iterations, saving checkpoints every {checkpoint_period} iterations to {CHECKPOINT_DIR}")
    print(f"9. Save the final model to {OUTPUT_DIR}/model_final.pth and configuration to {OUTPUT_DIR}/config.yaml")
    print(f"10. Create a model configuration JSON file at {OUTPUT_DIR}/model_config.json")
    print(f"11. Upload checkpoints to S3 path: s3://{S3_BUCKET}/{S3_PREFIX}checkpoints/")
    print(f"12. Upload the final model to S3 path: s3://{S3_BUCKET}/{S3_PREFIX}models/model_final.pth")
    print(f"13. Upload the configuration to S3 path: s3://{S3_BUCKET}/{S3_PREFIX}models/config.yaml")
    print(f"14. Upload the model configuration JSON to S3 path: s3://{S3_BUCKET}/{S3_PREFIX}models/model_config.json")
    print("\nSageMaker-specific configurations:")
    print(f"- DATALOADER.NUM_WORKERS: {num_workers}")
    print(f"- SOLVER.IMS_PER_BATCH: {ims_per_batch}")
    print(f"- SOLVER.BASE_LR: {base_lr}")
    print(f"- SOLVER.MAX_ITER: {max_iter}")
    print(f"- SOLVER.CHECKPOINT_PERIOD: {checkpoint_period}")
    print(f"- MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE: {roi_batch_size}")
    print("")

def download_s3_folder(s3_client, bucket, s3_path, local_dir):
    """Download all files from an S3 folder to a local directory with retry logic."""
    logger.info(f"Downloading from s3://{bucket}/{s3_path} to {local_dir}")
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    
    paginator = s3_client.get_paginator('list_objects_v2')
    for attempt in range(3):
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=s3_path):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    local_path = local_dir / Path(key).relative_to(s3_path)
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    s3_client.download_file(bucket, key, str(local_path))
                    logger.info(f"Downloaded {key} to {local_path}")
            return
        except ClientError as e:
            logger.error(f"Attempt {attempt + 1} failed to download S3 folder: {e}")
            time.sleep(2 ** attempt)
    raise Exception(f"Failed to download s3://{bucket}/{s3_path} after retries")

def download_pretrained_model(s3_client, bucket, s3_model_path, local_dir):
    """Download the pretrained model file from S3 with retry logic."""
    logger.info(f"Downloading pretrained model from s3://{bucket}/{s3_model_path} to {local_dir}")
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / 'model_final.pth'
    
    for attempt in range(3):
        try:
            s3_client.download_file(bucket, s3_model_path, str(local_path))
            logger.info(f"Downloaded pretrained model to {local_path}")
            return local_path
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"Pretrained model not found at s3://{bucket}/{s3_model_path}")
                return None
            logger.error(f"Attempt {attempt + 1} failed to download pretrained model: {e}")
            time.sleep(2 ** attempt)
    raise Exception(f"Failed to download s3://{bucket}/{s3_model_path} after retries")

def upload_to_s3(s3_client, local_path, bucket, s3_path):
    """Upload a file or directory to S3 with retry logic."""
    logger.info(f"Uploading {local_path} to s3://{bucket}/{s3_path}")
    local_path = Path(local_path)
    
    for attempt in range(3):
        try:
            if local_path.is_file():
                s3_client.upload_file(str(local_path), bucket, s3_path)
                logger.info(f"Uploaded {local_path} to s3://{bucket}/{s3_path}")
            elif local_path.is_dir():
                for item in local_path.rglob('*'):
                    if item.is_file():
                        relative_path = item.relative_to(local_path)
                        s3_key = f"{s3_path}/{relative_path}"
                        s3_client.upload_file(str(item), bucket, s3_key)
                        logger.info(f"Uploaded {item} to s3://{bucket}/{s3_key}")
            return
        except ClientError as e:
            logger.error(f"Attempt {attempt + 1} failed to upload to S3: {e}")
            time.sleep(2 ** attempt)
    raise Exception(f"Failed to upload {local_path} to s3://{bucket}/{s3_path}")

def load_checkpoint(cfg, trainer, s3_client):
    """Load the latest checkpoint from S3 if available."""
    checkpoint_s3_path = f"{S3_PREFIX}checkpoints/"
    checkpoint_local_dir = CHECKPOINT_DIR
    checkpoint_local_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        download_s3_folder(s3_client, S3_BUCKET, checkpoint_s3_path, checkpoint_local_dir)
        checkpoint_file = checkpoint_local_dir / 'last_checkpoint'
        if checkpoint_file.exists():
            with open(checkpoint_file, 'r') as f:
                checkpoint_path = checkpoint_local_dir / f.read().strip()
            if checkpoint_path.exists():
                logger.info(f"Resuming training from checkpoint: {checkpoint_path}")
                trainer.resume_or_load(resume=True)
                return True
        logger.info("No checkpoint found, starting training from scratch")
        return False
    except Exception as e:
        logger.warning(f"Failed to load checkpoint: {e}. Starting from scratch.")
        return False

def save_checkpoint(trainer, s3_client):
    """Save checkpoint to S3."""
    checkpoint_s3_path = f"{S3_PREFIX}checkpoints/"
    try:
        trainer.checkpointer.save('latest')
        upload_to_s3(s3_client, CHECKPOINT_DIR, S3_BUCKET, checkpoint_s3_path)
        logger.info(f"Saved checkpoint to s3://{S3_BUCKET}/{checkpoint_s3_path}")
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")

def train_layoutparser_model(json_path, image_dir, s3_client, hyperparameters):
    """Train the layout-parser model with checkpointing and S3 integration."""
    logger.info("Starting model training")
    dataset_name = "custom_layout_dataset"
    
    # Remove existing dataset if registered
    if dataset_name in DatasetCatalog:
        DatasetCatalog.remove(dataset_name)
        MetadataCatalog.remove(dataset_name)
    
    # Register the dataset
    logger.info(f"Registering dataset: {dataset_name} with JSON {json_path} and images {image_dir}")
    register_coco_instances(dataset_name, {}, str(json_path), image_dir)
    MetadataCatalog.get(dataset_name).thing_classes = list(LABEL_MAP.values())
    
    # Configure the model
    cfg = get_cfg()
    pretrained_model_s3_path = f"{S3_PREFIX}models/model_final.pth"
    pretrained_model_path = download_pretrained_model(s3_client, S3_BUCKET, pretrained_model_s3_path, PRETRAINED_DIR)
    
    if pretrained_model_path and pretrained_model_path.exists():
        logger.info(f"Using pretrained model from {pretrained_model_path}")
        cfg.merge_from_file(model_zoo.get_config_file("COCO-Detection/faster_rcnn_X_101_32x8d_FPN_3x.yaml"))
        cfg.MODEL.WEIGHTS = str(pretrained_model_path)
    else:
        logger.info("Using default pretrained weights from model zoo")
        cfg.merge_from_file(model_zoo.get_config_file("COCO-Detection/faster_rcnn_X_101_32x8d_FPN_3x.yaml"))
        cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url("COCO-Detection/faster_rcnn_X_101_32x8d_FPN_3x.yaml")
    
    # SageMaker-specific configurations from hyperparameters
    cfg.MODEL.DEVICE = DEVICE
    cfg.DATASETS.TRAIN = (dataset_name,)
    cfg.DATASETS.TEST = ()
    cfg.DATALOADER.NUM_WORKERS = int(hyperparameters.get('num_workers', 2))
    cfg.SOLVER.IMS_PER_BATCH = int(hyperparameters.get('ims_per_batch', 2))
    cfg.SOLVER.BASE_LR = float(hyperparameters.get('base_lr', 0.00025))
    cfg.SOLVER.MAX_ITER = int(hyperparameters.get('max_iter', 300))
    cfg.SOLVER.CHECKPOINT_PERIOD = int(hyperparameters.get('checkpoint_period', 100))
    cfg.MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE = int(hyperparameters.get('roi_batch_size', 128))
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = len(LABEL_MAP)
    cfg.OUTPUT_DIR = str(OUTPUT_DIR)
    
    # Create output directory
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    
    # Load checkpoint if available
    trainer = DefaultTrainer(cfg)
    load_checkpoint(cfg, trainer, s3_client)
    
    # Train the model
    try:
        trainer.train()
        logger.info("Training completed successfully")
    except Exception as e:
        logger.error(f"Training failed: {e}")
        save_checkpoint(trainer, s3_client)
        raise
    
    # Save final model and configuration
    model_path = OUTPUT_DIR / "model_final.pth"
    config_path = OUTPUT_DIR / "config.yaml"
    with open(config_path, "w") as f:
        f.write(cfg.dump())
    logger.info(f"Saved model to {model_path} and config to {config_path}")
    
    # Upload model to S3
    model_s3_path = f"{S3_PREFIX}models/model_final.pth"
    config_s3_path = f"{S3_PREFIX}models/config.yaml"
    upload_to_s3(s3_client, model_path, S3_BUCKET, model_s3_path)
    upload_to_s3(s3_client, config_path, S3_BUCKET, config_s3_path)
    
    # Create and save layout-parser model configuration
    model_config = {
        'config_path': str(config_path),
        'model_path': str(model_path),
        'label_map': LABEL_MAP,
        'extra_config': ["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.2],
        'device': DEVICE
    }
    config_json_path = OUTPUT_DIR / "model_config.json"
    with open(config_json_path, 'w') as f:
        json.dump(model_config, f)
    upload_to_s3(s3_client, config_json_path, S3_BUCKET, f"{S3_PREFIX}models/model_config.json")
    
    logger.info(f"Model and configuration uploaded to s3://{S3_BUCKET}/{S3_PREFIX}models/")

if __name__ == '__main__':
    # Load hyperparameters
    hyperparameters = load_hyperparameters()
    
    # Print all steps before execution
    print_training_steps(hyperparameters)
    
    # Initialize S3 client
    s3_client = boto3.client('s3')
    
    # Download training data from S3
    data_dir = Path('/opt/ml/input/data/training')
    download_s3_folder(s3_client, S3_BUCKET, f"{S3_PREFIX}data/", data_dir)
    
    # Find JSON and image directory
    json_path = next(data_dir.glob('*.json'), None)
    image_dir = data_dir / 'images'
    
    if not json_path or not image_dir.exists():
        logger.error("Training data not found in expected S3 location")
        raise FileNotFoundError("Training data not found")
    
    # Train the model
    train_layoutparser_model(json_path, image_dir, s3_client, hyperparameters)