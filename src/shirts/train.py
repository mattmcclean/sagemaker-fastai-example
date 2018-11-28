# Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import ast
import argparse
import logging
import os

from fastai import *
from fastai.vision import *
from fastai.callbacks import *

# ignore the PIL warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning) 

# setup the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# get the host from environment variable
HOSTNAME = os.environ.get('SM_CURRENT_HOST', 'train-host')

# define the fastai callback class to ouput metrics to CW logs for metrics
@dataclass
class MetricsLogger(LearnerCallback):
    # call when each epoch finishes to print the metrics
    def on_epoch_end(self, epoch: int, smooth_loss: Tensor, last_metrics: MetricsList, **kwargs: Any) -> bool:
        last_metrics = ifnone(last_metrics, [])
        stats = [(name, str(stat)) if isinstance(stat, int) else (name, f'{stat:.6f}')
                 for name, stat in zip(self.learn.recorder.names[1:], [smooth_loss] + last_metrics)]
        for m in stats:
            print(f'#quality_metric: host={HOSTNAME}, epoch={epoch}, {m[0]}={m[1]}')

# The train method
def _train(args):
    print(f'Called _train method with parameters:\n\t\tmodel arch: {args.model_arch}\n\t\tbatch size: {args.batch_size}\n\t\timage size: {args.image_size}\n\t\tepochs: {args.epochs}\n\t\tworkers: {args.workers}\n\t\tlearn rate: {args.lr}\n\t\tvalid pct: {args.valid_pct}')

    print(f'Resizing images from: {args.data_dir}')
    verify_images(args.data_dir+'/sport', max_size=int(300))
    verify_images(args.data_dir+'/metal', max_size=int(300))

    print(f'Getting training data from dir: {args.data_dir}')
    data = (ImageItemList.from_folder(args.data_dir)
            .random_split_by_pct(args.valid_pct)
            .label_from_folder()
            .transform(get_transforms(), size=args.image_size)
            .databunch(bs=args.batch_size, num_workers=args.workers)
            .normalize(imagenet_stats))
 
#    data = ImageDataBunch.from_folder(args.data_dir, train=".", valid_pct=args.valid_pct,
#                                      ds_tfms=get_transforms(), size=args.image_size, num_workers=args.workers,
#                                      bs=args.batch_size).normalize(imagenet_stats)
    
    print(f'Classes are {data.classes}')
    
    print(f'Model architecture is {args.model_arch}')
    arch = getattr(models, args.model_arch)
    print("Creating pretrained conv net")
    learn = create_cnn(data, arch, metrics=accuracy, callback_fns=[MetricsLogger])
    print("Fit four cycles with frozen model at lr=1e-2")
    learn.fit_one_cycle(4, 1e-2)
    print(f'Unfreeze and run {args.epochs} more cycles with lr={args.lr}')
    learn.unfreeze()
    learn.fit_one_cycle(args.epochs, max_lr=slice(args.lr/10,args.lr))
    path = Path(args.model_dir)
    print(f'Writing classes to model dir')
    save_texts(path/'classes.txt', data.classes)
    print(f'Saving model weights to dir: {args.model_dir}')
    
    trace_input = torch.ones(1,3,args.image_size,args.image_size).cuda()
    jit_model = torch.jit.trace(learn.model.float(), trace_input)
    torch.jit.save(jit_model, path/'f{args.model_arch}_jit')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--workers', type=int, default=4, metavar='W',
                        help='number of data loading workers (default: 4)')
    parser.add_argument('--epochs', type=int, default=2, metavar='E',
                        help='number of total epochs to run (default: 2)')
    parser.add_argument('--batch-size', type=int, default=64, metavar='BS',
                        help='batch size (default: 64)')
    parser.add_argument('--lr', type=float, default=3e-4, metavar='LR',
                        help='initial learning rate (default: 3e-4)')
    parser.add_argument('--valid-pct', type=float, default=0.2, metavar='VP',
                        help='validation data percentage (default: 20%)')    
    parser.add_argument('--momentum', type=float, default=0.9, metavar='M', help='momentum (default: 0.9)')
    parser.add_argument('--dist-backend', type=str, default='gloo', help='distributed backend (default: gloo)')

    # fast.ai specific parameters
    parser.add_argument('--image-size', type=int, default=224, metavar='IS',
                        help='image size (default: 224)')
    parser.add_argument('--model-arch', type=str, default='resnet34', metavar='MA',
                        help='model arch (default: resnet34)')
    
    # The parameters below retrieve their default values from SageMaker environment variables, which are
    # instantiated by the SageMaker containers framework.
    # https://github.com/aws/sagemaker-containers#how-a-script-is-executed-inside-the-container
    parser.add_argument('--hosts', type=str, default=ast.literal_eval(os.environ['SM_HOSTS']))
    parser.add_argument('--current-host', type=str, default=os.environ['SM_CURRENT_HOST'])
    parser.add_argument('--model-dir', type=str, default=os.environ['SM_MODEL_DIR'])
    parser.add_argument('--data-dir', type=str, default=os.environ['SM_CHANNEL_TRAINING'])
    parser.add_argument('--num-gpus', type=int, default=os.environ['SM_NUM_GPUS'])

    _train(parser.parse_args())
