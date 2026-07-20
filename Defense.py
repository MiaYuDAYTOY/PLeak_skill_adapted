import re
# from torchmetrics.text import Perplexity
from evaluate import load
from torcheval.metrics.text import Perplexity
class Defense:
    def __init__(self):
        self._creator = {}
        self._register_alias('None', self.no_defense)
        self._register_alias('Filter', self.filter_based)
        self._register_alias('Detector', self.detector_based)


    def _register_alias(self, name, creator):
        self._creator[name] = creator

    def no_defense(self, target, output):
        return output
    
    def filter_based(self, target, output):
        target = re.sub('[^a-zA-Z@]', ' ', target.lower())
        ret = ''
        for sent in output.split('.'):
            s = re.sub('[^a-zA-Z@]', ' ', sent.lower())
            if s in target:continue
            ret += s+'.'
        return ret

    def detector_based(self):
        pass

    def defend(self, name, **kwargs):
        creator = self._creator.get(name)
        return creator(**kwargs)
